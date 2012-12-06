"""
Tests for :mod:`otter.jsonschema.scaling_group`
"""
from copy import deepcopy

from twisted.trial.unittest import TestCase
from jsonschema import Draft3Validator, validate, ValidationError

from otter.json_schema import scaling_group


class ScalingGroupConfigTestCase(TestCase):
    """
    Simple verification that the JSON schema for scaling groups is correct.
    """
    def test_schema_valid(self):
        """
        The schema itself is valid Draft 3 schema
        """
        Draft3Validator.check_schema(scaling_group.config)

    def test_all_properties_have_descriptions(self):
        """
        All the properties in the schema should have descriptions
        """
        for property_name in scaling_group.config['properties']:
            prop = scaling_group.config['properties'][property_name]
            self.assertTrue('description' in prop)

    def test_valid_examples_validate(self):
        """
        The examples in the config examples all validate.
        """
        for example in scaling_group.config_examples:
            validate(example, scaling_group.config)

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
                                validate, invalid, scaling_group.config)

    def test_long_name_value_does_not_validate(self):
        """
        The name must be less than or equal to 256 characters.
        """
        invalid = {
            'name': ' ' * 257,
            'cooldown': 60,
            'minEntities': 1,
        }
        self.assertRaisesRegexp(ValidationError, "is too long",
                                validate, invalid, scaling_group.config)

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
                                    validate, base, scaling_group.config)


class GeneralLaunchConfigTestCase(TestCase):
    """
    Verification that the general JSON schema for launch configs is correct.
    """
    def test_schema_valid(self):
        """
        The schema itself is a valid Draft 3 schema
        """
        Draft3Validator.check_schema(scaling_group.launch_config)

    def test_must_have_lauch_server_type(self):
        """
        Without a launch server type, validation fails
        """
        self.assertRaisesRegexp(
            ValidationError, "'type' is a required property",
            validate, {"args": {"server": {}}}, scaling_group.launch_config)

    def test_invalid_launch_config_type_does_not_validate(self):
        """
        If a launch config type is provided that is not enum-ed, validation
        fails
        """
        self.assertRaisesRegexp(ValidationError, 'not of type',
                                validate, {'type': '_testtesttesttest'},
                                scaling_group.launch_config)

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
        schema = deepcopy(scaling_group.launch_config)
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
        for example in scaling_group.launch_server_config_examples:
            validate(example, scaling_group.launch_config)

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
                                    base, scaling_group.launch_server)
            # because the type schema fails to validate, the config schema
            # fails to validate because it is not the given type
            self.assertRaisesRegexp(ValidationError, 'not of type', validate,
                                    base, scaling_group.launch_config)

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
                                validate, invalid, scaling_group.launch_server)
        # because the type schema fails to validate, the config schema
        # fails to validate because it is not the given type
        self.assertRaisesRegexp(ValidationError, 'not of type',
                                validate, invalid, scaling_group.launch_config)

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
                                validate, invalid, scaling_group.launch_server)
        # because the type schema fails to validate, the config schema
        # fails to validate because it is not the given type
        self.assertRaisesRegexp(ValidationError, 'not of type',
                                validate, invalid, scaling_group.launch_config)


class ScalingPolicyTestCase(TestCase):
    """
    Simple verification that the JSON schema for scaling policies is correct.
    """
    def test_schema_valid(self):
        """
        The schema itself is a valid Draft 3 schema
        """
        Draft3Validator.check_schema(scaling_group.scaling_policy)
        Draft3Validator.check_schema(scaling_group.scaling_policy_creation)

    def test_valid_examples_validate(self):
        """
        The scaling policy and scaling policy creation examples all validate.
        """
        for example in scaling_group.scaling_policy_examples:
            validate(example, scaling_group.scaling_policy)
        for example in scaling_group.scaling_policy_creation_examples:
            validate(example, scaling_group.scaling_policy_creation)

    def test_either_change_or_changePercent(self):
        """
        A scaling policy can have either the attribute "change" or
        "changePercent", but not both
        """
        invalid = {
            "name": "",
            "change": 5,
            "changePercent": 5,
            "cooldown": 5
        }
        schemas = (
            scaling_group.scaling_policy,
            scaling_group.scaling_policy_creation)
        for schema in schemas:
            self.assertRaisesRegexp(ValidationError, 'not of type',
                                    validate, invalid, schema)

    def test_no_other_properties_valid(self):
        """
        Scaling policy can only have the following properties: name,
        change/changePercent, cooldown, and capabilityUrls.  Any other property
        results in an error.
        """
        invalid = {
            "name": "",
            "change": 5,
            "cooldown": 5,
            "poofy": False
        }
        schemas = (
            scaling_group.scaling_policy,
            scaling_group.scaling_policy_creation)
        for schema in schemas:
            self.assertRaisesRegexp(ValidationError, 'not of type',
                                    validate, invalid, schema)

    def test_non_creation_capability_urls_only_have_url_and_name(self):
        """
        Scaling policy capability url items can only have the following
        properties: name, url.  Any other property results in an error.
        """
        invalid = {
            "name": "",
            "url": "",
            "poofy": True
        }
        self.assertRaisesRegexp(
            ValidationError, 'not of type',
            validate, invalid, scaling_group.scaling_policy)

    def test_creation_capability_urls_are_names(self):
        """
        Scaling policy creation capability url items are names.
        """
        invalid = {"name": "", "url": ""}
        self.assertRaisesRegexp(
            ValidationError, 'not of type',
            validate, invalid, scaling_group.scaling_policy_creation)
