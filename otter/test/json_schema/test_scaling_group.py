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

    def test_extra_values_does_not_validate(self):
        """
        Providing non-expected properties will fail validate.
        """
        self.assertRaises(ValidationError, validate, {'what': 'not expected'},
                          scaling_group.config)

    def test_valid_examples_validate(self):
        """
        The examples in the config examples all validate.
        """
        for example in scaling_group.config_examples:
            validate(example, scaling_group.config)
