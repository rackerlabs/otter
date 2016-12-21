"""Tests for otter.cloud_client.cloudfeeds"""

from effect import sync_perform
from effect.testing import (
    EQFDispatcher, base_dispatcher, perform_sequence, sync_perform)

from twisted.trial.unittest import SynchronousTestCase

from otter.cloud_client import service_request
from otter.cloud_client import cloudfeeds as cf
from otter.constants import ServiceType
from otter.indexer import atom
from otter.test.cloud_client.test_init import service_request_eqf
from otter.test.utils import const, stub_json_response, stub_pure_response
from otter.util.pure_http import APIError, has_code


class CloudFeedsTests(SynchronousTestCase):
    """
    Tests for cloud feed functions.
    """
    def test_publish_autoscale_event(self):
        """
        Publish an event to cloudfeeds.  Successfully handle non-JSON data.
        """
        _log = object()
        eff = cf.publish_autoscale_event({'event': 'stuff'}, log=_log)
        expected = service_request(
            ServiceType.CLOUD_FEEDS, 'POST',
            'autoscale/events',
            headers={'content-type': ['application/vnd.rackspace.atom+json']},
            data={'event': 'stuff'}, log=_log, success_pred=has_code(201),
            json_response=False)

        # success
        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(stub_pure_response('<this is xml>', 201)))])
        resp, body = sync_perform(dispatcher, eff)
        self.assertEqual(body, '<this is xml>')

        # Add regression test that 202 should be an API error because this
        # is a bug in CF
        dispatcher = EQFDispatcher([(
            expected.intent,
            service_request_eqf(stub_pure_response('<this is xml>', 202)))])
        self.assertRaises(APIError, sync_perform, dispatcher, eff)


class ReadEntriesTests(SynchronousTestCase):

    entry = '<entry><summary>{}</summary></entry>'
    feed_fmt = (
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        '<link rel="{rel}" href="{rel_link}"/>'
        '{entries}</feed>')
    url = "http://url"
    directions = {"previous": cf.Direction.PREVIOUS,
                  "next": cf.Direction.NEXT}
    service_type = ServiceType.CLOUD_FEEDS

    def svc_intent(self, params={}):
        return service_request(
            self.service_type, "GET",
            self.url, params=params, json_response=False).intent

    def feed(self, rel, link, summaries):
        return self.feed_fmt.format(
            rel=rel, rel_link=link,
            entries=''.join(self.entry.format(s) for s in summaries))

    def _test_empty(self, rel):
        """
        Does not go further when there are no entries and return []
        """
        feedstr = self.feed(rel, "link-doesnt-matter", [])
        seq = [
            (self.svc_intent(), const(stub_json_response(feedstr)))
        ]
        entries_eff = cf.read_entries(
            self.service_type, self.url, {}, self.directions[rel])
        self.assertEqual(perform_sequence(seq, entries_eff), ([], {}))

    def test_empty_previous(self):
        self._test_empty("previous")

    def test_empty_next(self):
        self._test_empty("next")

    def _test_single_page(self, rel):
        """
        Collects entries and goes to next link if there are entries and returns
        if next one is empty
        """
        feed1str = self.feed(rel, "https://url?page=2", ["summary1", "summ2"])
        feed2str = self.feed(rel, "link", [])
        seq = [
            (self.svc_intent({"a": "b"}), const(stub_json_response(feed1str))),
            (self.svc_intent({"page": ['2']}),
             const(stub_json_response(feed2str)))
        ]
        entries, params = perform_sequence(
            seq,
            cf.read_entries(
                self.service_type, self.url, {"a": "b"}, self.directions[rel]))
        self.assertEqual(
            [atom.summary(entry) for entry in entries],
            ["summary1", "summ2"])
        self.assertEqual(params, {"page": ["2"]})

    def test_single_page_previous(self):
        self._test_single_page("previous")

    def test_single_page_next(self):
        self._test_single_page("next")

    def _test_multiple_pages(self, rel):
        """
        Collects entries and goes to next link if there are entries and
        continues until next link returns empty list
        """
        feed1_str = self.feed(rel, "https://url?page=2", ["summ1", "summ2"])
        feed2_str = self.feed(rel, "https://url?page=3", ["summ3", "summ4"])
        feed3_str = self.feed(rel, "link", [])
        seq = [
            (self.svc_intent(), const(stub_json_response(feed1_str))),
            (self.svc_intent({"page": ['2']}),
             const(stub_json_response(feed2_str))),
            (self.svc_intent({"page": ['3']}),
             const(stub_json_response(feed3_str))),
        ]
        entries, params = perform_sequence(
            seq,
            cf.read_entries(
                self.service_type, self.url, {}, self.directions[rel]))
        self.assertEqual(
            [atom.summary(entry) for entry in entries],
            ["summ1", "summ2", "summ3", "summ4"])
        self.assertEqual(params, {"page": ["3"]})

    def test_multiple_pages_previous(self):
        self._test_multiple_pages("previous")

    def test_multiple_pages_next(self):
        self._test_multiple_pages("next")

    def _test_no_link(self, rel):
        """
        Returns entries collected till now if there is no rel link
        """
        feedstr = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            '<entry><summary>summary</summary></entry></feed>')
        seq = [
            (self.svc_intent({"a": "b"}), const(stub_json_response(feedstr)))
        ]
        entries, params = perform_sequence(
            seq,
            cf.read_entries(
                self.service_type, self.url, {"a": "b"}, self.directions[rel]))
        self.assertEqual(atom.summary(entries[0]), "summary")
        self.assertEqual(params, {"a": "b"})

    def test_no_link_previous(self):
        self._test_no_link("previous")

    def test_no_link_next(self):
        self._test_no_link("next")

    def test_invalid_direction(self):
        """
        Calling `read_entries` with invalid direction raises ValueError
        """
        self.assertRaises(
            ValueError, sync_perform, base_dispatcher,
            cf.read_entries(self.service_type, self.url, {}, "bad"))
