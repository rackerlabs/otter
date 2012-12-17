"""
Integration-y tests for the REST interface interacting with the mock model.

This is perhaps not the place for these tests to go.  Also, perhaps this should
instead be tested by spinning up an actually HTTP server (thus this test can
happen using the mock tap file).

But until a decision has been made for integration test infrastructure and
frameworks, this will do for now, as it is needed to verify that the rest unit
tests and mock model unit tests do not lie.
"""

import json
from urlparse import urlsplit

from twisted.trial.unittest import TestCase

from otter.models.interface import NoSuchScalingGroupError
from otter.models.mock import MockScalingGroupCollection
from otter.rest.application import set_store

from otter.test.rest.request import request
from otter.test.utils import DeferredTestMixin


class MockStoreRestTestCase(DeferredTestMixin, TestCase):
    """
    Test case for testing the REST API against various the mock model.

    This could be made a base case instead, and different implementations of
    the model interfaces should be tested using a subclass of this base case.

    The store should be cleared between every test case and the test fixture
    reloaded at the start of every test case.

    The plan for the case of a DB is that an object can be created that starts
    up a DB, knows how to clear it, load particular fixtures, etc.  Each test
    case can be passed to a function in this instance that loads a fixture
    before every test method (or not), and cleans up after every test calling
    the test case's `addCleanup` method.  Then, the object will shut down the
    DB process when `trial` finishes its run.

    That way the same DB object can be used for other integration tests as well
    (not just this test case), and so the DB only needs to be started once.

    In the case of in-memory stores, fixtures can be loaded and duplicated.
    """

    skip = "All broken"

    def setUp(self):
        """
        Replace the store every time with a clean one.
        """
        store = MockScalingGroupCollection()
        store.mock_add_tenant('11111')
        set_store(store)

    def _create_and_view_scaling_group(self):
        """
        Creating a scaling group with a valid config returns with a 200 OK and
        a Location header pointing to the new scaling group.
        """
        config = {
            'name': 'created',
            'cooldown': 10,
            'minEntities': 1,
            'maxEntities': 8,
            'metadata': {
                'somekey': 'somevalue'
            }
        }

        wrapper = self.assert_deferred_succeeded(
            request('POST', '/v1.0/11111/groups/dfw',
                    body=json.dumps(config)))

        self.assertEqual(wrapper.response.code, 201,
                         "Create failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "")

        headers = wrapper.response.headers.getRawHeaders('Location')
        self.assertTrue(headers is not None)
        self.assertEqual(1, len(headers))
        # now make sure the Location header points to something good!
        path = urlsplit(headers[0])[2].rstrip('/')

        wrapper = self.assert_deferred_succeeded(request('GET', path))
        self.assertEqual(wrapper.response.code, 200)
        self.assertEqual(json.loads(wrapper.content), config)

        return path

    def _edit_and_view_scaling_group(self, path):
        """
        Editing the config of a scaling group with a valid config returns with
        a 204 no content.  The next attempt to view the scaling group should
        return the new config.
        """
        config = {
            'name': 'edited',
            'cooldown': 5,
            'minEntities': 3,
            'maxEntities': 10,
            'metadata': {
                'anotherkey': 'anothervalue'
            }
        }

        wrapper = self.assert_deferred_succeeded(
            request('PUT', path, body=json.dumps(config)))

        self.assertEqual(wrapper.response.code, 204,
                         "Edit failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "")

        # now try to view
        wrapper = self.assert_deferred_succeeded(request('GET', path))
        self.assertEqual(wrapper.response.code, 200)
        self.assertEqual(json.loads(wrapper.content), config)

    def _delete_and_view_scaling_group(self, path):
        """
        Deleting a scaling group returns with a 204 no content.  The next
        attempt to view the scaling group should return a 404 not found.
        """
        wrapper = self.assert_deferred_succeeded(request('DELETE', path))
        self.assertEqual(wrapper.response.code, 204,
                         "Delete failed: {0}".format(wrapper.content))
        self.assertEqual(wrapper.content, "")

        # now try to view
        wrapper = self.assert_deferred_succeeded(request('GET', path))
        self.assertEqual(wrapper.response.code, 404)

        # flush any logged errors
        self.flushLoggedErrors(NoSuchScalingGroupError)

    def assert_number_of_scaling_groups(self, number):
        """
        Asserts that there are ``number`` number of scaling groups
        """
        wrapper = self.assert_deferred_succeeded(
            request('GET', '/v1.0/11111/groups'))
        self.assertEqual(200, wrapper.response.code)

        all_groups = json.loads(wrapper.content)
        groups = [group for region in all_groups.values() for group in region]
        self.assertEqual(len(groups), number)

    def test_crud(self):
        """
        Start with no scaling groups.  Create one, make sure it's listed.
        View the config, edit the config, then delete it and make sure its
        no longer listed.
        """
        # start with no scaling groups
        self.assert_number_of_scaling_groups(0)
        path = self._create_and_view_scaling_group()

        # there should be one scaling group now
        self.assert_number_of_scaling_groups(1)
        self._edit_and_view_scaling_group(path)

        # there should still be one scaling group
        self.assert_number_of_scaling_groups(1)
        self._delete_and_view_scaling_group(path)

        # there should be no scaling groups now
        self.assert_number_of_scaling_groups(0)
