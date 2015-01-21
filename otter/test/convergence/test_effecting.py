"""Tests for convergence effecting."""
from inspect import getargspec

from characteristic import attributes, NOTHING
from effect import parallel
from mock import ANY
from twisted.trial.unittest import SynchronousTestCase
from zope.interface import implementer

from otter.constants import ServiceType
from otter.convergence.effecting import _reqs_to_effect, steps_to_effect
from otter.convergence.steps import IStep, Request
from otter.http import get_request_func, service_request
from otter.test.utils import defaults_by_name
from otter.util.pure_http import has_code


@attributes(["service_type", "method", "url", "headers", "data", "log",
             "reauth_codes", "success_pred", "json_response"],
            defaults={"headers": None,
                      "data": None,
                      "log": ANY,
                      "reauth_codes": (401, 403),
                      "success_pred": has_code(200),
                      "json_response": True})
class _PureRequestStub(object):
    """
    A bound request stub, suitable for testing.

    NOTE: This is not used in this test module any more. Delete once it's
    unused.
    """


class PureRequestStubTests(SynchronousTestCase):
    """
    Tests for :class:`_PureRequestStub`, the request func test double.
    """
    def test_signature_and_defaults(self):
        """
        Compare the test double to the real thing.
        """
        authenticator, log, = object(), object()
        request_func = get_request_func(authenticator, 1234, log, {}, "XYZ")
        args = getargspec(request_func).args
        characteristic_attrs = _PureRequestStub.characteristic_attributes
        self.assertEqual(set(a.name for a in characteristic_attrs), set(args))
        characteristic_defaults = {a.name: a.default_value
                                   for a in characteristic_attrs
                                   if a.default_value is not NOTHING}
        self.assertEqual(characteristic_defaults,
                         defaults_by_name(request_func))


class RequestsToEffectTests(SynchronousTestCase):
    """
    Tests for converting :class:`Request` into effects.
    """

    def assertCompileTo(self, conv_requests, expected_effects):
        """
        Assert that the given convergence requests compile down to a parallel
        effect comprised of the given effects.
        """
        effect = _reqs_to_effect(conv_requests)
        self.assertEqual(effect, parallel(expected_effects))

    def test_single_request(self):
        """
        A single request is correctly compiled down to an effect.
        """
        conv_requests = [
            Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                    method="GET",
                    path="/whatever",
                    success_pred=has_code(999))]
        expected_effects = [
            service_request(
                service_type=ServiceType.CLOUD_LOAD_BALANCERS,
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
                    success_pred=has_code(231))]
        expected_effects = [
            service_request(
                service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                method="GET",
                url="/whatever",
                headers=None,
                data=None),
            service_request(
                service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                method="GET",
                url="/whatever/something/else",
                headers=None,
                data=None,
                success_pred=has_code(231))]
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
                    success_pred=has_code(231)),
            Request(service=ServiceType.CLOUD_SERVERS,
                    method="POST",
                    path="/xyzzy",
                    data=data_sentinel)]
        expected_effects = [
            service_request(
                service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                method="GET",
                url="/whatever",
                headers=None,
                data=None),
            service_request(
                service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                method="GET",
                url="/whatever/something/else",
                headers=None,
                data=None,
                success_pred=has_code(231)),
            service_request(
                service_type=ServiceType.CLOUD_SERVERS,
                method="POST",
                url="/xyzzy",
                headers=None,
                data=data_sentinel)]
        self.assertCompileTo(conv_requests, expected_effects)


@implementer(IStep)
class Steppy(object):
    """A dummy step."""
    def as_request(self):
        """Return a simple GET .../whatever on CLOUD_LOAD_BALANCERS"""
        return Request(service=ServiceType.CLOUD_LOAD_BALANCERS,
                       method="GET",
                       path="whatever")


class StepsToEffectTests(SynchronousTestCase):
    """Tests for :func:`steps_to_effect`"""
    def test_uses_step_request(self):
        """Steps are converted to requests."""
        steps = [Steppy(), Steppy()]
        expected_effects = [
            service_request(
                service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                method="GET",
                url="whatever",
                headers=None,
                data=None),
            service_request(
                service_type=ServiceType.CLOUD_LOAD_BALANCERS,
                method="GET",
                url="whatever",
                headers=None,
                data=None),
        ]
        effect = steps_to_effect(steps)
        self.assertEqual(effect, parallel(expected_effects))
