"""
Test to create and update the created group.
"""
from test_repo.autoscale.fixtures import AutoscaleFixture
from cloudcafe.common.tools.datagen import rand_name


class UpdateGroupConfigTest(AutoscaleFixture):
    """
    Verify update group.
    """
    #AUTO-303

    @classmethod
    def setUpClass(cls):
        """
        Create a scaling group.
        """
        super(UpdateGroupConfigTest, cls).setUpClass()
        create_resp = cls.autoscale_behaviors.create_scaling_group_given(
            gc_min_entities=2,
            gc_max_entities=10)
        cls.group = create_resp.entity
        cls.resources.add(cls.group.id,
                          cls.autoscale_client.delete_scaling_group)
        cls.gc_name = rand_name('updgroupconfig')
        cls.gc_min_entities = cls.group.groupConfiguration.minEntities
        cls.gc_cooldown = 800
        cls.gc_max_entities = 15
        cls.gc_metadata = {'upd_key1': 'upd_value1'}

    @classmethod
    def tearDownClass(cls):
        """
        Delete the scaling group.
        """
        super(UpdateGroupConfigTest, cls).tearDownClass()

    def test_update_minentities_to_be_the_same(self):
        """
        Verify update with an incomplete request containing minentities to be the same,
        fails with 400
        """
        upd_group_resp = self.autoscale_client.update_group_config(
            self.group.id,
            name=self.group.groupConfiguration.name,
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=self.group.groupConfiguration.minEntities)
        self.assertEquals(upd_group_resp.status_code, 400,
                          msg='Update failed with {0} as it does not include full request'
                          .format(upd_group_resp.status_code))

    def test_update_minentities_only(self):
        """
        Verify update with an incomplete request containing minentities only,
        fails with 400
        """
        upd_min_entities = 3
        upd_group_resp = self.autoscale_client.update_group_config(
            self.group.id,
            name=self.group.groupConfiguration.name,
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=upd_min_entities)
        self.assertEquals(upd_group_resp.status_code, 400,
                          msg='Update failed with {0} as it does not include full request'
                          .format(upd_group_resp.status_code))

    def test_update_minentities_over_maxentities(self):
        """
        Verify update with an incomplete request containing minentities over maxentities,
        fails with 400
        """
        #AUTO-302
        upd_min_entities = 25
        upd_group_resp = self.autoscale_client.update_group_config(
            self.group.id,
            name=self.group.groupConfiguration.name,
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=upd_min_entities,
            max_entities=self.group.groupConfiguration.maxEntities,
            metadata={})
        self.assertEquals(upd_group_resp.status_code, 400,
                          msg='Update failed with {0} as it does not include full request'
                          .format(upd_group_resp.status_code))

    def test_update_maxentities_lessthan_minentities(self):
        """
        Verify update with an incomplete request containing maxentities under minentities,
        fails with 400
        """
        #AUTO-302
        upd_max_entities = 0
        upd_group_resp = self.autoscale_client.update_group_config(
            self.group.id,
            name=self.group.groupConfiguration.name,
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=self.group.groupConfiguration.maxEntities,
            max_entities=upd_max_entities,
            metadata={})
        self.assertEquals(upd_group_resp.status_code, 400,
                          msg='Update failed with {0} as it does not include full request'
                          .format(upd_group_resp.status_code))

    def test_update_maxentities_only(self):
        """
        Verify update with an incomplete request containing maxentities only,
        fails with 400
        """
        upd_max_entities = 5
        upd_group_resp = self.autoscale_client.update_group_config(
            self.group.id,
            name=self.group.groupConfiguration.name,
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=self.group.groupConfiguration.minEntities,
            max_entities=upd_max_entities)
        self.assertEquals(upd_group_resp.status_code, 400,
                          msg='Update failed with {0} as it does not include full request'
                          .format(upd_group_resp.status_code))

    def test_update_metadata_only(self):
        """
        Verify update with an incomplete request containing metadata only, fails with 400
        """
        upd_metadata = {'does this': 'work'}
        upd_group_resp = self.autoscale_client.update_group_config(
            self.group.id,
            name=self.group.groupConfiguration.name,
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=self.group.groupConfiguration.minEntities,
            metadata=upd_metadata)
        self.assertEquals(upd_group_resp.status_code, 400,
                          msg='Update failed with {0} as it does not include full request'
                          .format(upd_group_resp.status_code))

    def test_update_metadata_to_be_none(self):
        """
        Verify update with request containing null metadata
        """
        upd_metadata = {}
        upd_group_resp = self.autoscale_client.update_group_config(
            self.group.id,
            name=self.group.groupConfiguration.name,
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=self.group.groupConfiguration.minEntities,
            max_entities=self.group.groupConfiguration.maxEntities,
            metadata=upd_metadata)
        self.assertEquals(upd_group_resp.status_code, 204,
                          msg='Update failed with {0}'
                          .format(upd_group_resp.status_code))
        get_upd_group = self.autoscale_client.\
            view_scaling_group_config(group_id=self.group.id)
        self.assertEquals(get_upd_group.status_code, 200)
        get_group_config = get_upd_group.entity
        self.assertEquals(get_group_config.metadata, upd_metadata)
        self.assertEquals(get_group_config.maxEntities, 10)
        self.assertEquals(get_group_config.minEntities, 2)
        self.assertEquals(get_group_config.cooldown,
                          self.group.groupConfiguration.cooldown)
        upd_group_resp = self.autoscale_client.update_group_config(
            self.group.id,
            name=self.group.groupConfiguration.name,
            cooldown=self.group.groupConfiguration.cooldown,
            min_entities=self.group.groupConfiguration.minEntities,
            max_entities=self.group.groupConfiguration.maxEntities)
        self.assertEquals(upd_group_resp.status_code, 400,
                          msg='Update failed with {0} as it does not include full request'
                          .format(upd_group_resp.status_code))

    def test_update_group_config_response(self):
        """
        Verify update for response code 204, header and data
        """
        update_group_response = self.autoscale_client.update_group_config(
            group_id=self.group.id,
            name=self.gc_name,
            cooldown=self.gc_cooldown,
            min_entities=self.gc_min_entities,
            max_entities=self.gc_max_entities,
            metadata=self.gc_metadata)
        group_config_response = self.autoscale_client.view_scaling_group_config(
            self.group.id)
        updated_config = group_config_response.entity
        self.assertEquals(update_group_response.status_code, 204,
                          msg='Update group config failed with {0}'
                          .format(update_group_response.status_code))
        self.validate_headers(update_group_response.headers)
        self.assertEquals(updated_config.minEntities, self.gc_min_entities,
                          msg='Min entities in the Group config did not update')
        self.assertEquals(updated_config.cooldown, self.gc_cooldown,
                          msg='Cooldown time in the Group config did not update')
        self.assertEquals(updated_config.name, self.gc_name,
                          msg='Name in the Group config did not update')
        self.assertEquals(updated_config.maxEntities, self.gc_max_entities,
                          msg='Max entities in the Group config did not update')
        self.assertEquals(
            self.autoscale_behaviors.to_data(updated_config.metadata),
            self.gc_metadata,
            msg='Metadata in the Group config did not update')
