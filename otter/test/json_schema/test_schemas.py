"""
Tests for :mod:`otter.jsonschema.group_schemas`
"""
from copy import deepcopy

from twisted.trial.unittest import TestCase
from jsonschema import Draft3Validator, validate, ValidationError

from otter.json_schema import group_schemas, group_examples, rest_schemas


class ScalingGroupConfigTestCase(TestCase):
    """
    Simple verification that the JSON schema for scaling groups is correct.
    """
    def test_schema_valid(self):
        """
        The schema itself is valid Draft 3 schema
        """
        Draft3Validator.check_schema(group_schemas.config)

    def test_all_properties_have_descriptions(self):
        """
        All the properties in the schema should have descriptions
        """
        for property_name in group_schemas.config['properties']:
            prop = group_schemas.config['properties'][property_name]
            self.assertTrue('description' in prop)

    def test_valid_examples_validate(self):
        """
        The examples in the config examples all validate.
        """
        for example in group_examples.config():
            validate(example, group_schemas.config)

    def test_extra_values_does_not_validate(self):
        """
        Providing non-expected properties will fail validate.
        """
        invalid = {
            'name': 'who',
            'cooldown': 60,
            'minEntities': 1,
            'what': 'not expected'
        }
        self.assertRaisesRegexp(ValidationError, "Additional properties",
                                validate, invalid, group_schemas.config)

    def test_long_name_value_does_not_validate(self):
        """
        The name must be less than or equal to 256 characters.
        """
        invalid = {
            'name': 'a' * 257,
            'cooldown': 60,
            'minEntities': 1,
        }
        self.assertRaisesRegexp(ValidationError, "is too long",
                                validate, invalid, group_schemas.config)

    def test_invalid_name_does_not_validate(self):
        """
        The name must contain something other than whitespace.
        """
        invalid = {
            'name': ' ',
            'cooldown': 60,
            'minEntities': 1,
        }
        for invalid_name in ('', ' ', '    '):
            invalid['name'] = invalid_name
            self.assertRaisesRegexp(ValidationError, "does not match",
                                    validate, invalid, group_schemas.config)

    def test_invalid_metadata_does_not_validate(self):
        """
        Metadata keys and values must be strings of less than or equal to 256
        characters.  Anything else will fail to validate.
        """
        base = {
            'name': "stuff",
            'cooldown': 60,
            'minEntities': 1
        }
        invalids = [
            # because Draft 3 doesn't support key length, so it's a regexp
            ({'key' * 256: ""}, "Additional properties"),
            ({'key': "value" * 256}, "is too long"),
            ({'key': 1}, "not of type"),
            ({'key': None}, "not of type")
        ]
        for invalid, error_regexp in invalids:
            base['metadata'] = invalid
            self.assertRaisesRegexp(ValidationError, error_regexp,
                                    validate, base, group_schemas.config)


class GeneralLaunchConfigTestCase(TestCase):
    """
    Verification that the general JSON schema for launch configs is correct.
    """
    def test_schema_valid(self):
        """
        The schema itself is a valid Draft 3 schema
        """
        Draft3Validator.check_schema(group_schemas.launch_config)

    def test_must_have_lauch_server_type(self):
        """
        Without a launch server type, validation fails
        """
        self.assertRaisesRegexp(
            ValidationError, "'type' is a required property",
            validate, {"args": {"server": {}}}, group_schemas.launch_config)

    def test_invalid_launch_config_type_does_not_validate(self):
        """
        If a launch config type is provided that is not enum-ed, validation
        fails
        """
        self.assertRaisesRegexp(ValidationError, 'not of type',
                                validate, {'type': '_testtesttesttest'},
                                group_schemas.launch_config)

    def test_other_launch_config_type(self):
        """
        Test use of union types by adding another launch config type and
        seeing if that validates.
        """
        other_type = {
            "type": "object",
            "description": "Tester launch config type",
            "properties": {
                "type": {
                    "enum": ["_testtesttesttest"]
                },
                "args": {}
            }
        }
        schema = deepcopy(group_schemas.launch_config)
        schema['type'].append(other_type)
        validate({"type": "_testtesttesttest", "args": {"what": "who"}},
                 schema)


class ServerLaunchConfigTestCase(TestCase):
    """
    Simple verification that the JSON schema for launch server launch configs
    is correct.
    """
    def test_valid_examples_validate(self):
        """
        The launch server config examples all validate.
        """
        for example in group_examples.launch_server_config():
            validate(example, group_schemas.launch_config)

    def test_invalid_load_balancer_does_not_validate(self):
        """
        Load balancers need to have 2 values: loadBalancerId and port.
        """
        base = {
            "type": "launch_server",
            "args": {
                "server": {}
            }
        }
        invalids = [
            {'loadBalancerId': '', 'port': 80},
            {'loadBalancerId': 3, 'port': '80'}
        ]
        for invalid in invalids:
            base["args"]["loadBalancers"] = [invalid]
            # the type fails ot valdiate because of 'not of type'
            self.assertRaisesRegexp(ValidationError, 'not of type', validate,
                                    base, group_schemas.launch_server)
            # because the type schema fails to validate, the config schema
            # fails to validate because it is not the given type
            self.assertRaisesRegexp(ValidationError, 'not of type', validate,
                                    base, group_schemas.launch_config)

    def test_duplicate_load_balancers_do_not_validate(self):
        """
        If the same load balancer config appears twice, the launch config
        fails to validate.
        """
        invalid = {
            "type": "launch_server",
            "args": {
                "server": {},
                "loadBalancers": [
                    {'loadBalancerId': 1, 'port': 80},
                    {'loadBalancerId': 1, 'port': 80}
                ]
            }
        }
        # the type fails ot valdiate because of the load balancers are not
        # unique
        self.assertRaisesRegexp(ValidationError, 'non-unique elements',
                                validate, invalid, group_schemas.launch_server)
        # because the type schema fails to validate, the config schema
        # fails to validate because it is not the given type
        self.assertRaisesRegexp(ValidationError, 'not of type',
                                validate, invalid, group_schemas.launch_config)

    def test_unspecified_args_do_not_validate(self):
        """
        If random attributes to args are provided, the launch config fails to
        validate
        """
        invalid = {
            "type": "launch_server",
            "args": {
                "server": {},
                "hat": "top"
            }
        }
        # the type fails ot valdiate because of the additional 'hat' property
        self.assertRaisesRegexp(ValidationError, 'Additional properties',
                                validate, invalid, group_schemas.launch_server)
        # because the type schema fails to validate, the config schema
        # fails to validate because it is not the given type
        self.assertRaisesRegexp(ValidationError, 'not of type',
                                validate, invalid, group_schemas.launch_config)

    def test_no_args_do_not_validate(self):
        """
        If no arguments are provided, the launch config fails to validate
        """
        invalid = {
            "type": "launch_server",
            "args": {}
        }
        self.assertRaisesRegexp(
            ValidationError, "'server' is a required property",
            validate, invalid, group_schemas.launch_server)
        self.assertRaisesRegexp(ValidationError, 'not of type',
                                validate, invalid, group_schemas.launch_config)


class ScalingPolicyTestCase(TestCase):
    """
    Simple verification that the JSON schema for scaling policies is correct.
    """
    def test_schema_valid(self):
        """
        The schema itself is a valid Draft 3 schema
        """
        Draft3Validator.check_schema(group_schemas.policy)

    def test_valid_examples_validate(self):
        """
        The scaling policy examples all validate.
        """
        for example in group_examples.policy():
            validate(example, group_schemas.policy)

    def test_either_change_or_changePercent_or_desiredCapacity(self):
        """
        A scaling policy can have one of the attribute "change" or "changePercent"
        or "desiredCapacity", but not any 2 or 3 of them
        """
        invalid = {
            "name": "meh",
            "cooldown": 5
        }
        invalid1 = invalid.copy().update({'change': 3, 'changePercent': 23})
        invalid2 = invalid.copy().update({'change': 3, 'desiredCapacity': 23})
        invalid3 = invalid.copy().update({'changePercent': 3, 'desiredCapacity': 23})
        invalid4 = invalid.copy().update({'change': 4, 'changePercent': 3, 'desiredCapacity': 23})
        for invalid in [invalid1, invalid2, invalid3, invalid4]:
            self.assertRaisesRegexp(
                ValidationError, 'not of type',
                validate, invalid, group_schemas.policy)

    def test_desired_negative(self):
        """
        A scaling policy cannot have a negative "desiredCapacity" attribute
        """
        invalid = {
            "name": "aname",
            "desiredCapacity": -5,
            "cooldown": 5,
            "type": "webhook"
        }
        self.assertRaisesRegexp(
            ValidationError, 'is less than the minimum of 0',
            validate, invalid, group_schemas.policy)

    def test_no_other_properties_valid(self):
        """
        Scaling policy can only have the following properties: name,
        change/changePercent/desiredCapacity, cooldown, type, and capabilityUrls.
        Any other property results in an error.
        """
        invalid = {
            "name": "aname",
            "change": 5,
            "cooldown": 5,
            "type": "webhook",
            "poofy": False
        }
        self.assertRaisesRegexp(
            ValidationError, 'is not of type',
            validate, invalid, group_schemas.policy)

    def test_type_set(self):
        """
        Scaling policy can only have the following properties: name,
        change/changePercent/desiredCapacity, cooldown, type, and capabilityUrls.
        Ensure that if the type is not present, that's an error.
        """
        invalid = {
            "name": "aname",
            "change": 5,
            "cooldown": 5
        }
        self.assertRaisesRegexp(
            ValidationError, "'type' is a required property",
            validate, invalid, group_schemas.policy)

    def test_type_valid(self):
        """
        Scaling policy have a type value that has enum validation.
        Make sure it works.
        """
        invalid = {
            "name": "aname",
            "change": 5,
            "cooldown": 5,
            "type": "blah"
        }
        self.assertRaisesRegexp(
            ValidationError, 'is not one of',
            validate, invalid, group_schemas.policy)

    def test_invalid_name_does_not_validate(self):
        """
        The name must contain something other than whitespace.
        """
        invalid = {
            "name": "",
            "change": 10,
            "cooldown": 5,
            "type": "webhook"
        }
        for invalid_name in ('', ' ', '    '):
            invalid['name'] = invalid_name
            self.assertRaisesRegexp(
                ValidationError, 'does not match', validate, invalid,
                group_schemas.policy)


class CreateScalingGroupTestCase(TestCase):
    """
    Simple verification that the JSON schema for creating a scaling group is
    correct.
    """
    def test_schema_valid(self):
        """
        The schema itself is a valid Draft 3 schema
        """
        Draft3Validator.check_schema(rest_schemas.create_group_request)

    def test_valid_examples_validate(self):
        """
        The scaling policy examples all validate.
        """
        for example in rest_schemas.create_group_request_examples:
            validate(example, rest_schemas.create_group_request)

    def test_wrong_launch_config_fails(self):
        """
        Not including a launchConfiguration or including an invalid ones will
        fail to validate.
        """
        invalid = {'groupConfiguration': group_examples.config()[0]}
        self.assertRaisesRegexp(
            ValidationError, 'launchConfiguration',
            validate, invalid, rest_schemas.create_group_request)
        invalid['launchConfiguration'] = {}
        self.assertRaises(ValidationError,
                          validate, invalid, rest_schemas.create_group_request)

    def test_wrong_group_config_fails(self):
        """
        Not including a groupConfiguration or including an invalid ones will
        fail to validate.
        """
        invalid = {'launchConfiguration':
                   group_examples.launch_server_config()[0]}
        self.assertRaisesRegexp(
            ValidationError, 'groupConfiguration',
            validate, invalid, rest_schemas.create_group_request)
        invalid['groupConfiguration'] = {}
        self.assertRaises(ValidationError,
                          validate, invalid, rest_schemas.create_group_request)

    def test_wrong_scaling_policy_fails(self):
        """
        An otherwise ok creation blob fails if the provided scaling policies
        are wrong.
        """
        self.assertRaises(
            ValidationError, validate, {
                'groupConfiguration': group_examples.config()[0],
                'launchConfiguration':
                group_examples.launch_server_config()[0],
                'scalingPolicies': {"Hello!": "Yes quite."}
            }, rest_schemas.create_group_request)
