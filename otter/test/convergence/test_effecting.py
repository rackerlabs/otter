"""Tests for convergence effecting."""
from characteristic import attributes

from effect import parallel

from twisted.trial.unittest import SynchronousTestCase

from otter.constants import ServiceType
from otter.convergence.effecting import _reqs_to_effect
from otter.convergence.steps import Request
from otter.util.pure_http import has_code


@attributes(["service_type", "method", "url", "headers", "data", "success_pred"],
            defaults={"success_pred": has_code(200)})
class _PureRequestStub(object):
    """
    A bound request stub, suitable for testing.
    """


class RequestsToEffectTests(SynchronousTestCase):
    """
    Tests for converting :class:`Request` into effects.
    """

    def assertCompileTo(self, conv_requests, expected_effects):
        """
        Assert that the given convergence requests compile down to a parallel
        effect comprised of the given effects.
        """
        effect = _reqs_to_effect(_PureRequestStub, conv_requests)
        self.assertEqual(effect, parallel(expected_effects))

    def test_single_request(self):
        """
        A single request is correctly compiled down to an effect.
        """
        conv_requests = [
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever",
                    success_codes=(999,))]
        expected_effects = [
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever",
                             headers=None,
                             data=None,
                             success_pred=has_code(999))]
        self.assertCompileTo(conv_requests, expected_effects)

    def test_multiple_requests(self):
        """
        Multiple requests of the same type are correctly compiled down to an
        effect.
        """
        conv_requests = [
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever"),
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever/something/else",
                    success_codes=(231,))]
        expected_effects = [
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever",
                             headers=None,
                             data=None),
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever/something/else",
                             headers=None,
                             data=None,
                             success_codes=(231,))]
        self.assertCompileTo(conv_requests, expected_effects)

    def test_multiple_requests_of_different_type(self):
        """
        Multiple requests of different types are correctly compiled down to
        an effect.
        """
        data_sentinel = object()
        conv_requests = [
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever"),
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever/something/else",
                    success_codes=(231,)),
            Request(service=ServiceType.CLOUD_SERVERS,
                    method="POST",
                    path="/xyzzy",
                    data=data_sentinel)]
        expected_effects = [
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever",
                             headers=None,
                             data=None),
            _PureRequestStub(service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                             method="GET",
                             url="/whatever/something/else",
                             headers=None,
                             data=None,
                             success_codes=(231,)),
            _PureRequestStub(service_type=ServiceType.CLOUD_SERVERS,
                             method="POST",
                             url="/xyzzy",
                             headers=None,
                             data=data_sentinel)]
        self.assertCompileTo(conv_requests, expected_effects)
