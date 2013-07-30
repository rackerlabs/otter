"""
Tests for :mod:`otter.jsonschema.group_schemas`
"""
from copy import deepcopy
from datetime import datetime, timedelta

from twisted.trial.unittest import TestCase
from jsonschema import Draft3Validator, ValidationError

from otter.json_schema import validate
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

    def test_min_cooldown(self):
        """
        Cooldown must be >= 0
        """
        invalid = {
            'name': ' ',
            'cooldown': -1,
            'minEntities': 0,
        }
        self.assertRaisesRegexp(ValidationError, "less than the minimum",
                                validate, invalid, group_schemas.config)

    def test_max_cooldown(self):
        """
        Cooldown must be <= group_schemas.MAX_COOLDOWN
        """
        invalid = {
            'name': ' ',
            'cooldown': group_schemas.MAX_COOLDOWN + 1,
            'minEntities': 0,
        }
        self.assertRaisesRegexp(ValidationError, "greater than the maximum",
                                validate, invalid, group_schemas.config)


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

    def setUp(self):
        """
        Store copies of schedule type policies
        """
        self.at_policy = deepcopy(group_examples.policy()[3])
        self.cron_policy = deepcopy(group_examples.policy()[4])

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
        _invalid = {
            "name": "meh",
            "cooldown": 5,
            "type": "webhook"
        }
        for props in [{'change': 3, 'changePercent': 23},
                      {'change': 3, 'desiredCapacity': 23},
                      {'changePercent': 3, 'desiredCapacity': 23},
                      {'change': 4, 'changePercent': 3, 'desiredCapacity': 23}]:
            invalid = _invalid.copy()
            invalid.update(props)
            self.assertRaisesRegexp(
                ValidationError, 'not of type',
                validate, invalid, group_schemas.policy)

    def test_change_zero(self):
        """
        A scaling policy cannot have 'change' as 0
        """
        invalid = {
            "name": "meh",
            "cooldown": 5,
            "type": "webhook",
            "change": 0
        }
        self.assertRaisesRegexp(
            ValidationError, 'is disallowed for 0',
            validate, invalid, group_schemas.policy)

        del invalid['change']
        invalid['changePercent'] = 0.0
        self.assertRaisesRegexp(
            ValidationError, 'is disallowed for 0.0',
            validate, invalid, group_schemas.policy)

    def test_changepercent_zero(self):
        """
        A scaling policy cannot have 'changePercent' as 0.0
        """
        invalid = {
            "name": "meh",
            "cooldown": 5,
            "type": "webhook",
            "changePercent": 0.0
        }
        self.assertRaisesRegexp(
            ValidationError, 'is disallowed for 0.0',
            validate, invalid, group_schemas.policy)

    def test_desired_zero(self):
        """
        A scaling policy CAN have 'desiredCapacity' as 0
        """
        valid = {
            "name": "meh",
            "cooldown": 5,
            "type": "webhook",
            "desiredCapacity": 0
        }
        validate(valid, group_schemas.policy)

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
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

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

    def test_min_cooldown(self):
        """
        Cooldown must be >= 0
        """
        invalid = {
            "name": "",
            "change": -1,
            "cooldown": 5,
            "type": "webhook"
        }
        self.assertRaisesRegexp(ValidationError, "does not match",
                                validate, invalid, group_schemas.policy)

    def test_max_cooldown(self):
        """
        Cooldown must be <= group_schemas.MAX_COOLDOWN
        """
        invalid = {
            "name": "",
            "change": 10,
            "cooldown": group_schemas.MAX_COOLDOWN + 1,
            "type": "webhook"
        }
        self.assertRaisesRegexp(ValidationError, "does not match",
                                validate, invalid, group_schemas.policy)

    def test_schedule_no_args(self):
        """
        Schedule policy must have 'args'
        """
        invalid = self.at_policy
        del invalid['args']
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_args_when_no_schedule(self):
        """
        args can be there only when type is 'schedule'
        """
        invalid = self.at_policy
        invalid['type'] = 'webhook'
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_schedule_no_change(self):
        """
        Schedule policy must have 'change', 'changePercent' or 'desiredCapacity'
        """
        invalid = self.at_policy
        del invalid['changePercent']
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_excess_in_args(self):
        """
        Args cannot have anything other than 'at' or 'cron'
        """
        invalid = self.at_policy
        invalid['args']['junk'] = 2
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_only_one_in_args(self):
        """
        Args can have only one of 'at' or 'cron'; not both
        """
        invalid = self.at_policy
        invalid['args']['cron'] = '* * * * *'
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_empty_args(self):
        """
        Args cannot be empty
        """
        invalid = self.at_policy
        invalid['args'] = {}
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_invalid_timestamp(self):
        """
        policy with invalid timestamp raises ``ValidationError``
        """
        invalid = self.at_policy
        invalid_dates = ['', 'junk']
        for invalid_date in invalid_dates:
            invalid['args']['at'] = invalid_date
            self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_only_date_timestamp(self):
        """
        policy with only date in timestamp raises ``ValidationError``
        """
        invalid = self.at_policy
        invalid['args']['at'] = '2012-10-10'
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_only_time_timestamp(self):
        """
        policy with only time in timestamp raises ``ValidationError``
        """
        invalid = self.at_policy
        invalid['args']['at'] = '11:25'
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_localtime_timestamp(self):
        """
        policy with localtime in timestamp raises ``ValidationError``
        """
        invalid = self.at_policy
        invalid['args']['at'] = '2012-10-20T11:25:00'
        self.assertRaisesRegexp(ValueError, 'Expecting Zulu-format UTC time',
                                group_schemas.validate_datetime, invalid['args']['at'])
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_past_timestamp(self):
        """
        policy with past date raises `ValidationError`
        """
        invalid = self.at_policy
        past = datetime.utcnow() - timedelta(days=1)
        invalid['args']['at'] = past.isoformat() + 'Z'
        self.assertRaisesRegexp(ValueError, 'time must be in future',
                                group_schemas.validate_datetime, invalid['args']['at'])
        self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_valid_UTC_timestamp(self):
        """
        policy with valid UTC timestamp validates
        """
        valid = self.at_policy
        future = datetime.utcnow() + timedelta(days=1)
        valid['args']['at'] = future.isoformat() + 'Z'
        group_schemas.validate_datetime(valid['args']['at'])
        validate(valid, group_schemas.policy)

    def test_valid_cron(self):
        """
        policy with valid cron entry validates
        """
        valid_crons = ['* * * * *', '0-59 0-23 1-31 1-12 0-6', '00 9,16 * * *',
                       '00 02-11 * * *', '00 09-18 * * 1-5', '0 0 0 0 0']
        valid = self.cron_policy
        for valid_cron in valid_crons:
            valid['args']['cron'] = valid_cron
            validate(valid, group_schemas.policy)

    def test_invalid_cron(self):
        """
        policy with invalid cron entry raises ``ValidationError``
        """
        invalid_crons = ['', 'junk', '* * -32 * *', '-90 * * *', '* 0 * *',
                         '* * * * * *', '0 * * 0 * *', '* * * *', '* * * * * * * *',
                         '*12345', 'dfsdfdf', '- - - - -', '-090 * * * *', '* -089 * * *']
        invalid = self.cron_policy
        for invalid_cron in invalid_crons:
            invalid['args']['cron'] = invalid_cron
            self.assertRaises(ValidationError, validate, invalid, group_schemas.policy)

    def test_cron_with_seconds(self):
        """
        policy with cron having 6 entries representing seconds is not allowed
        """
        # This is tested for validation in above test.
        # Here it is checked for correct exception rased
        invalid_cron = '* * * * * *'
        self.assertRaisesRegexp(ValueError, 'Seconds not allowed',
                                group_schemas.validate_cron, invalid_cron)


class CreateScalingPoliciesTestCase(TestCase):
    """
    Verification that the JSON schema for creating scaling policies is correct
    """
    one_policy = group_examples.policy()[0]

    def test_schema_valid(self):
        """
        The schema itself is a valid Draft 3 schema
        """
        Draft3Validator.check_schema(rest_schemas.create_policies_request)

    def test_empty_array_valid(self):
        """
        Seems pointless to disallow empty arrays, so empty arrays validate.
        """
        validate([], rest_schemas.create_policies_request)

    def test_duplicate_policies_valid(self):
        """
        Duplicate policies are valid
        """
        validate([self.one_policy] * 5,
                 rest_schemas.create_policies_request)

    def test_non_array_policy_fails(self):
        """
        A single policy, not in an array, fails to validate.
        """
        self.assertRaises(ValidationError, validate, self.one_policy,
                          rest_schemas.create_policies_request)


class CreateScalingGroupTestCase(TestCase):
    """
    Simple verification that the JSON schema for creating a scaling group is
    correct.
    """
    def setUp(self):
        self.policy = group_examples.policy()[0]
        self.config = group_examples.config()[0]
        self.launch = group_examples.launch_server_config()[0]

    def test_schema_valid(self):
        """
        The schema itself is a valid Draft 3 schema
        """
        Draft3Validator.check_schema(rest_schemas.create_group_request)

    def test_creation_with_no_scaling_policies_valid(self):
        """
        Seems pointless to disallow empty arrays, so empty arrays validate.
        """
        validate({
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch
        }, rest_schemas.create_group_request)

    def test_creation_with_empty_scaling_policies_valid(self):
        """
        Seems pointless to disallow empty arrays, so empty arrays validate.
        """
        validate({
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch,
            'scalingPolicies': []
        }, rest_schemas.create_group_request)

    def test_creation_with_scaling_policies_valid(self):
        """
        Seems pointless to disallow empty arrays, so empty arrays validate.
        """
        validate({
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch,
            'scalingPolicies': [self.policy]
        }, rest_schemas.create_group_request)

    def test_creation_with_duplicate_scaling_policies_valid(self):
        """
        Seems pointless to disallow empty arrays, so empty arrays validate.
        """
        validate({
            'groupConfiguration': self.config,
            'launchConfiguration': self.launch,
            'scalingPolicies': [self.policy] * 5
        }, rest_schemas.create_group_request)

    def test_wrong_launch_config_fails(self):
        """
        Not including a launchConfiguration or including an invalid ones will
        fail to validate.
        """
        invalid = {'groupConfiguration': self.config}
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
        invalid = {'launchConfiguration': self.launch}
        self.assertRaisesRegexp(
            ValidationError, 'groupConfiguration',
            validate, invalid, rest_schemas.create_group_request)
        invalid['groupConfiguration'] = {}
        self.assertRaises(ValidationError,
                          validate, invalid, rest_schemas.create_group_request)

    def test_wrong_scaling_policy_fails(self):
        """
        An otherwise ok creation blob fails if the provided scaling policies
        are wrong (not an array of policies).
        """
        for wrong_policy in (self.policy, {"Hello!": "Yes quite."}, 'what'):
            self.assertRaises(
                ValidationError, validate, {
                    'groupConfiguration': self.config,
                    'launchConfiguration': self.launch,
                    'scalingPolicies': wrong_policy
                }, rest_schemas.create_group_request)


class CreateWebhookTestCase(TestCase):
    """
    Verify the webhook schema.
    """
    def test_schema_valid(self):
        """
        The webhook schema is valid JSON Schema Draft 3.
        """
        Draft3Validator.check_schema(group_schemas.webhook)

    def test_name_required(self):
        """
        Name is required.
        """
        invalid = {'metadata': {'foo': 'bar'}}
        self.assertRaises(ValidationError, validate, invalid, group_schemas.webhook)

    def test_metadata_optional(self):
        """
        Metadata is optional.
        """
        validate({'name': 'foo'}, group_schemas.webhook)


class UpdateWebhookTestCase(TestCase):
    """
    Verify the update webhook schemas.
    """

    def test_schema_valid(self):
        """
        The update webhook schema is valid JSON Schema Draft 3.
        """
        Draft3Validator.check_schema(group_schemas.update_webhook)

    def test_name_required(self):
        """
        Name is required.
        """
        invalid = {'metadata': {'foo': 'bar'}}
        self.assertRaises(ValidationError, validate, invalid, group_schemas.update_webhook)

    def test_required_metadata(self):
        """
        Metadata is required on updates.
        """
        invalid = {'name': 'foo'}
        self.assertRaises(ValidationError, validate, invalid, group_schemas.update_webhook)
