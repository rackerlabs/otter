"""
Tests for :mod:`otter.jsonschema.scaling_group`
"""

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


class LaunchConfigTestCase(TestCase):
    """
    Simple verification that the JSON schema for launch configs is correct.
    """
    pass
