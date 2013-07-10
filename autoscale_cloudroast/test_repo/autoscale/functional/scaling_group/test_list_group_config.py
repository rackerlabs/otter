"""
Test to verify list group config.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cloudcafe.compute.common.datagen import rand_name


class ListGroupConfigTest(AutoscaleFixture):

    """
    Verify list group config.
    """

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group with given data.
        """
        super(ListGroupConfigTest, cls).setUpClass()
        gc_name = rand_name('t_sg')
        cls.gc_name = gc_name
        cls.gc_max_entities = 10
        cls.gc_metadata = {'gc_meta_key_1': 'gc_meta_value_1',
                           'gc_meta_key_2': 'gc_meta_value_2'}
        create_resp = cls.autoscale_behaviors.create_scaling_group_given(
            gc_name=cls.gc_name,
            gc_max_entities=cls.gc_max_entities,
            gc_metadata=cls.gc_metadata)
        cls.group = create_resp.entity
        cls.resources.add(cls.group.id,
                          cls.autoscale_client.delete_scaling_group)
        cls.group_config_response = cls.autoscale_client.view_scaling_group_config(
            cls.group.id)
        cls.group_config = cls.group_config_response.entity

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group.
        """
        super(ListGroupConfigTest, cls).tearDownClass()

    def test_list_group_config_response(self):
        """
        Verify the list group config for response code 200, headers and data
        """
        self.assertEquals(self.group_config_response.status_code, 200,
                          msg='List group config failed with {0}'
                          .format(self.group_config_response.status_code))
        self.validate_headers(self.group_config_response.headers)
        self.assertEquals(self.group_config.minEntities,
                          self.gc_min_entities,
                          msg='Min entities in the Group config did not match')
        self.assertEquals(self.group_config.cooldown,
                          self.gc_cooldown,
                          msg='Cooldown time in the Group config did not match')
        self.assertEquals(self.group_config.name, self.gc_name,
                          msg='Name in the Group config did not match')
        self.assertEquals(self.group_config.maxEntities,
                          self.gc_max_entities,
                          msg='Max entities in the Group config did not match')
        self.assertEquals(
            self.autoscale_behaviors.to_data(self.group_config.metadata),
            self.gc_metadata,
            msg='Metadata in the Group config did not match')
