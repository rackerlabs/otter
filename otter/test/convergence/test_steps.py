"""Tests for convergence steps."""
import json
from uuid import uuid4

from effect import Effect, Func, base_dispatcher, sync_perform
from effect.testing import SequenceDispatcher, perform_sequence

from mock import ANY, patch

from pyrsistent import freeze, pmap, pset, thaw

from testtools.matchers import ContainsAll

from twisted.trial.unittest import SynchronousTestCase

from otter.cloud_client import (
    CLBDeletedError,
    CLBDuplicateNodesError,
    CLBImmutableError,
    CLBNodeLimitError,
    CLBNotActiveError,
    CLBNotFoundError,
    CLBRateLimitError,
    CreateServerConfigurationError,
    CreateServerOverQuoteError,
    NoSuchCLBError,
    NoSuchCLBNodeError,
    NoSuchServerError,
    NovaComputeFaultError,
    NovaRateLimitError,
    ServerMetadataOverLimitError,
    check_stack,
    create_stack,
    delete_stack,
    has_code,
    service_request,
    update_stack)
from otter.constants import ServiceType
from otter.convergence.model import (
    CLBDescription,
    CLBNodeCondition,
    CLBNodeType,
    ErrorReason,
    StepResult)
from otter.convergence.steps import (
    AddNodesToCLB,
    BulkAddToRCv3,
    BulkRemoveFromRCv3,
    ChangeCLBNode,
    CheckStack,
    ConvergeLater,
    CreateServer,
    CreateStack,
    DeleteServer,
    DeleteStack,
    FailConvergence,
    RemoveNodesFromCLB,
    SetMetadataItemOnServer,
    UnexpectedServerStatus,
    UpdateStack,
    _RCV3_LB_DOESNT_EXIST_PATTERN,
    _RCV3_LB_INACTIVE_PATTERN,
    _RCV3_NODE_ALREADY_A_MEMBER_PATTERN,
    _RCV3_NODE_NOT_A_MEMBER_PATTERN,
    _rcv3_check_bulk_add,
    _rcv3_check_bulk_delete,
    delete_and_verify,
)
from otter.log.intents import Log
from otter.test.cloud_client.test_init import log_intent
from otter.test.utils import (
    StubResponse,
    matches,
    noop,
    raise_,
    resolve_effect,
    stack,
    stub_pure_response,
    transform_eq)
from otter.util.hashkey import generate_server_name
from otter.util.http import APIError
from otter.util.retry import (
    Retry, ShouldDelayAndRetry, exponential_backoff_interval, retry_times)


def service_request_error_response(error):
    """
    Returns the error response that gets passed to error handlers on the
    service request effect.

    That is, (type of error, actual error, traceback object)

    Just returns None for the traceback object.
    """
    return (type(error), error, None)


class CreateServerTests(SynchronousTestCase):
    """
    Tests for :obj:`CreateServer.as_effect`.
    """

    def test_create_server_request_with_name(self):
        """
        :obj:`CreateServer.as_effect` produces a request for creating a server.
        If the name is given, a randomly generated suffix is appended to the
        server name.
        """
        create = CreateServer(
            server_config=freeze({'server': {'name': 'myserver',
                                             'flavorRef': '1'}}))
        eff = create.as_effect()
        self.assertEqual(eff.intent, Func(generate_server_name))
        eff = resolve_effect(eff, 'random-name')
        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data={'server': {'name': 'myserver-random-name',
                                 'flavorRef': '1'}},
                success_pred=has_code(202),
                reauth_codes=(401,)).intent)

    def test_create_server_noname(self):
        """
        :obj:`CreateServer.as_effect`, when no name is provided in the launch
        config, will generate the name will from scratch.

        This only verifies intent; result reporting is tested in
        :meth:`test_create_server`.
        """
        create = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}}))
        eff = create.as_effect()
        self.assertEqual(eff.intent, Func(generate_server_name))
        eff = resolve_effect(eff, 'random-name')
        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data={'server': {'name': 'random-name', 'flavorRef': '1'}},
                success_pred=has_code(202),
                reauth_codes=(401,)).intent)

    def test_create_server_success_case(self):
        """
        :obj:`CreateServer.as_effect`, when it results in a successful create,
        returns with :obj:`StepResult.RETRY`.
        """
        eff = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}})).as_effect()
        seq = [
            (Func(generate_server_name), lambda _: 'random-name'),
            (service_request(
                ServiceType.CLOUD_SERVERS,
                'POST',
                'servers',
                data={'server': {'name': 'random-name', 'flavorRef': '1'}},
                success_pred=has_code(202),
                reauth_codes=(401,)).intent,
             lambda _: (StubResponse(202, {}), {"server": {}})),
            (Log('request-create-server', ANY), lambda _: None)
        ]
        self.assertEqual(
            perform_sequence(seq, eff),
            (StepResult.RETRY,
             [ErrorReason.String('waiting for server to become active')]))

    def _assert_create_server_with_errs_has_status(self, exceptions, status):
        """
        Helper function to make a :class:`CreateServer` effect, and resolve
        it with the provided exceptions, asserting that the result is the
        provided status, with the reason being the exception.
        """
        eff = CreateServer(
            server_config=freeze({'server': {'flavorRef': '1'}})).as_effect()
        eff = resolve_effect(eff, 'random-name')

        for exc in exceptions:
            self.assertEqual(
                resolve_effect(eff, service_request_error_response(exc),
                               is_error=True),
                (status, [ErrorReason.Exception(
                    matches(ContainsAll([type(exc), exc])))])
            )

    def test_create_server_terminal_failures(self):
        """
        :obj:`CreateServer.as_effect`, when it results in
        :class:`CreateServerConfigurationError` or
        :class:`CreateServerOverQuoteError` or a :class:`APIError` with
        a 400 failure code, returns with :obj:`StepResult.FAILURE`
        """
        errs = (
            CreateServerConfigurationError(
                "Bad networks format: network uuid is not in proper format "
                "(2b55377-890e-4fc9-9ece-ad5a414a788e)"),
            CreateServerConfigurationError("This was just a bad request"),
            CreateServerOverQuoteError(
                "Quota exceeded for ram: Requested 1024, but already used "
                "131072 of 131072 ram"),
            APIError(code=400, body="Unparsable user error", headers={}),
            APIError(code=418, body="I am a teapot but this is still a 4xx",
                     headers={})
        )
        self._assert_create_server_with_errs_has_status(
            errs, StepResult.FAILURE)

    def test_create_server_retryable_failures(self):
        """
        :obj:`CreateServer.as_effect`, when it results in a
        :class:`NovaComputeFaultError` or :class:`NovaRateLimitError` or
        :class:`APIError` that is not a 4xx, returns with a
        :obj:`StepResult.RETRY`
        """
        errs = (
            NovaComputeFaultError("oops"),
            NovaRateLimitError("OverLimit Retry..."),
            APIError(code=501, body=":(", headers={}),
            TypeError("You did something wrong")
        )
        self._assert_create_server_with_errs_has_status(errs, StepResult.RETRY)


class DeleteServerTests(SynchronousTestCase):
    """
    Tests for :obj:`DeleteServer`
    """

    @patch('otter.convergence.steps.delete_and_verify')
    def test_delete_server(self, mock_dav):
        """
        :obj:`DeleteServer.as_effect` calls `delete_and_verify` with
        retries. It returns SUCCESS on completion and RETRY on failure
        """
        mock_dav.side_effect = lambda sid: Effect(sid)
        eff = DeleteServer(server_id='abc123').as_effect()
        self.assertIsInstance(eff.intent, Retry)
        self.assertEqual(
            eff.intent.should_retry,
            ShouldDelayAndRetry(can_retry=retry_times(3),
                                next_interval=exponential_backoff_interval(2)))
        self.assertEqual(eff.intent.effect.intent, 'abc123')

        self.assertEqual(
            resolve_effect(eff, (None, {})),
            (StepResult.RETRY,
             [ErrorReason.String('must re-gather after deletion in order to '
                                 'update the active cache')]))

    def test_delete_and_verify_del_404(self):
        """
        :func:`delete_and_verify` invokes server delete and succeeds on 404
        """
        eff = delete_and_verify('sid')
        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_SERVERS, 'DELETE', 'servers/sid',
                success_pred=has_code(404)).intent)
        self.assertEqual(resolve_effect(eff, (ANY, {})), (ANY, {}))

    def test_delete_and_verify_del_fails(self):
        """
        :func:`delete_and_verify` fails if delete server fails
        """
        eff = delete_and_verify('sid')
        self.assertRaises(
            APIError,
            resolve_effect,
            eff,
            service_request_error_response(APIError(500, '')),
            is_error=True)

    def test_delete_and_verify_del_fails_non_apierror(self):
        """
        :func:`delete_and_verify` fails if delete server fails with error
        other than APIError
        """
        eff = delete_and_verify('sid')
        self.assertRaises(
            ValueError,
            resolve_effect,
            eff,
            service_request_error_response(ValueError('meh')),
            is_error=True)

    def test_delete_and_verify_verifies(self):
        """
        :func:`delete_and_verify` verifies if the server task_state has changed
        to "deleting" after successful delete server call and succeeds if that
        has happened. The details call succeeds if it returns 404
        """
        eff = delete_and_verify('sid')
        eff = resolve_effect(
            eff, service_request_error_response(APIError(204, {})),
            is_error=True)

        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_SERVERS, 'GET', 'servers/sid',
                success_pred=has_code(200, 404)).intent)
        r = resolve_effect(
            eff,
            (StubResponse(200, {}),
             {'server': {"OS-EXT-STS:task_state": 'deleting'}}))
        self.assertIsNone(r)

    def test_delete_and_verify_verify_404(self):
        """
        :func:`delete_and_verify` gets server details after successful delete
        and succeeds if get server details returns 404
        """
        eff = delete_and_verify('sid')
        eff = resolve_effect(
            eff, service_request_error_response(APIError(204, {})),
            is_error=True)
        r = resolve_effect(eff, (StubResponse(404, {}), {"itemNotFound": {}}))
        self.assertIsNone(r)

    def test_delete_and_verify_verify_unexpectedstatus(self):
        """
        :func:`delete_and_verify` raises `UnexpectedServerStatus` error
        if server status returned after deleting is not "deleting"
        """
        eff = delete_and_verify('sid')
        eff = resolve_effect(
            eff, service_request_error_response(APIError(204, {})),
            is_error=True)
        self.assertRaises(
            UnexpectedServerStatus,
            resolve_effect,
            eff,
            (StubResponse(200, {}),
             {'server': {"OS-EXT-STS:task_state": 'bad'}})
        )


class StepAsEffectTests(SynchronousTestCase):
    """
    Tests for converting :obj:`IStep` implementations to :obj:`Effect`s.
    """
    def test_set_metadata_item(self):
        """
        :obj:`SetMetadataItemOnServer.as_effect` produces a request for
        setting a metadata item on a particular server.  It succeeds if
        successful, but does not fail for any errors.
        """
        server_id = u'abc123'
        meta = SetMetadataItemOnServer(server_id=server_id, key='metadata_key',
                                       value='teapot')
        eff = meta.as_effect()
        seq = [
            (eff.intent, lambda i: (StubResponse(202, {}), {})),
            (Log(ANY, ANY), lambda _: None)
        ]
        self.assertEqual(
            perform_sequence(seq, eff),
            (StepResult.SUCCESS, []))

        exceptions = (NoSuchServerError("msg", server_id=server_id),
                      ServerMetadataOverLimitError("msg", server_id=server_id),
                      NovaRateLimitError("msg"),
                      APIError(code=500, body="", headers={}))
        for exception in exceptions:
            self.assertRaises(
                type(exception),
                perform_sequence,
                [(eff.intent, lambda i: raise_(exception))],
                eff)

    def _change_node_eff(self):
        change_node = ChangeCLBNode(
            lb_id='abc123',
            node_id='node1',
            condition=CLBNodeCondition.DRAINING,
            weight=50,
            type=CLBNodeType.PRIMARY)
        return change_node.as_effect()

    def test_change_load_balancer_node(self):
        """
        :obj:`ChangeCLBNode.as_effect` produces a request for
        modifying a load balancer node.
        """
        eff = self._change_node_eff()
        retry_result = (
            StepResult.RETRY,
            [ErrorReason.String(
                'must re-gather after CLB change in order to update the '
                'active cache')])
        seq = [(eff.intent, lambda i: (StubResponse(202, {}), {}))]
        self.assertEqual(perform_sequence(seq, eff), retry_result)

    def test_change_clb_node_terminal_errors(self):
        """Some errors during :obj:`ChangeCLBNode` make convergence fail."""
        eff = self._change_node_eff()
        terminal = (NoSuchCLBNodeError(lb_id=u'abc123', node_id=u'node1'),
                    CLBNotFoundError(lb_id=u'abc123'),
                    APIError(code=400, body="", headers={}))
        for exception in terminal:
            self.assertEqual(
                perform_sequence([(eff.intent, lambda i: raise_(exception))],
                                 eff),
                (StepResult.FAILURE, [ANY]))

    def test_change_clb_node_nonterminal_errors(self):
        """Some errors during :obj:`ChangeCLBNode` make convergence retry."""
        eff = self._change_node_eff()
        nonterminal = (APIError(code=500, body="", headers={}),
                       CLBNotActiveError(lb_id=u'abc123'),
                       CLBRateLimitError(lb_id=u'abc123'))
        for exception in nonterminal:
            self.assertEqual(
                perform_sequence([(eff.intent, lambda i: raise_(exception))],
                                 eff),
                (StepResult.RETRY, ANY))

    def test_add_nodes_to_clb(self):
        """
        :obj:`AddNodesToCLB` produces a request for adding any number of nodes
        to a cloud load balancer.
        """
        lb_id = "12345"
        lb_nodes = pset([
            ('1.2.3.4', CLBDescription(lb_id=lb_id, port=80)),
            ('1.2.3.4', CLBDescription(lb_id=lb_id, port=8080)),
            ('2.3.4.5', CLBDescription(lb_id=lb_id, port=80))
        ])
        step = AddNodesToCLB(lb_id=lb_id, address_configs=lb_nodes)
        eff = step.as_effect()

        self.assertEqual(
            eff.intent,
            service_request(
                ServiceType.CLOUD_LOAD_BALANCERS,
                'POST',
                "loadbalancers/12345/nodes",
                json_response=True,
                success_pred=ANY,
                data={"nodes": ANY}).intent)

        node_data = sorted(eff.intent.data['nodes'],
                           key=lambda n: (n['address'], n['port']))
        self.assertEqual(node_data, [
            {'address': '1.2.3.4',
             'port': 80,
             'condition': 'ENABLED',
             'type': 'PRIMARY',
             'weight': 1},
            {'address': '1.2.3.4',
             'port': 8080,
             'condition': 'ENABLED',
             'type': 'PRIMARY',
             'weight': 1},
            {'address': '2.3.4.5',
             'port': 80,
             'condition': 'ENABLED',
             'type': 'PRIMARY',
             'weight': 1}
        ])

    def _add_one_node_to_clb(self):
        """
        Return an effect from adding nodes to CLB.  Uses 1 default node.
        """
        lb_id = "12345"
        lb_nodes = pset([('1.2.3.4', CLBDescription(lb_id=lb_id, port=80))])
        step = AddNodesToCLB(lb_id=lb_id, address_configs=lb_nodes)
        return step.as_effect()

    def test_add_nodes_to_clb_success_response_codes(self):
        """
        :obj:`AddNodesToCLB` succeeds on 202.
        """
        eff = self._add_one_node_to_clb()
        seq = SequenceDispatcher([
            (eff.intent, lambda i: (StubResponse(202, {}), '')),
            (Log(ANY, ANY), lambda _: None)
        ])
        expected = (
            StepResult.RETRY,
            [ErrorReason.String('must re-gather after adding to CLB in order '
                                'to update the active cache')])

        with seq.consume():
            self.assertEquals(sync_perform(seq, eff), expected)

    def test_add_nodes_to_clb_non_terminal_failures(self):
        """
        :obj:`AddNodesToCLB` retries if the CLB is temporarily locked, or if
        the request was rate-limited, or if there were duplicate nodes, or if
        there was an API error and the error is unknown but not a 4xx.
        """
        non_terminals = (CLBDuplicateNodesError(lb_id=u"12345"),
                         CLBImmutableError(lb_id=u"12345"),
                         CLBRateLimitError(lb_id=u"12345"),
                         APIError(code=500, body="oops!"),
                         TypeError("You did something wrong in your code."))
        eff = self._add_one_node_to_clb()

        for exc in non_terminals:
            seq = SequenceDispatcher([(eff.intent, lambda i: raise_(exc))])
            with seq.consume():
                self.assertEquals(
                    sync_perform(seq, eff),
                    (StepResult.RETRY, [ErrorReason.Exception(
                        matches(ContainsAll([type(exc), exc])))]))

    def test_add_nodes_to_clb_terminal_failures(self):
        """
        :obj:`AddNodesToCLB` fails if the CLB is not found or deleted, or
        if there is any other 4xx error, then
        the error is propagated up and the result is a failure.
        """
        terminals = (CLBNotFoundError(lb_id=u"12345"),
                     CLBDeletedError(lb_id=u"12345"),
                     NoSuchCLBError(lb_id=u"12345"),
                     CLBNodeLimitError(lb_id=u"12345", node_limit=25),
                     APIError(code=403, body="You're out of luck."),
                     APIError(code=422, body="Oh look another 422."))
        eff = self._add_one_node_to_clb()

        for exc in terminals:
            seq = SequenceDispatcher([(eff.intent, lambda i: raise_(exc))])
            with seq.consume():
                self.assertEquals(
                    sync_perform(seq, eff),
                    (StepResult.FAILURE, [ErrorReason.Exception(
                        matches(ContainsAll([type(exc), exc])))]))

    def test_remove_nodes_from_clb(self):
        """
        :obj:`RemoveNodesFromCLB` produces a request for deleting any number of
        nodes from a cloud load balancer.
        """
        lb_id = "12345"
        node_ids = [str(i) for i in range(5)]

        step = RemoveNodesFromCLB(lb_id=lb_id, node_ids=pset(node_ids))
        request = step.as_effect()
        self.assertEqual(
            request.intent,
            service_request(
                ServiceType.CLOUD_LOAD_BALANCERS,
                'DELETE',
                "loadbalancers/12345/nodes",
                params={'id': transform_eq(sorted, node_ids)},
                json_response=True,
                success_pred=ANY).intent)

    def test_remove_nodes_from_clb_predicate(self):
        """
        :obj:`RemoveNodesFromCLB` only succeeds on 202.
        """
        lb_id = "12345"
        node_ids = [str(i) for i in range(5)]
        step = RemoveNodesFromCLB(lb_id=lb_id, node_ids=pset(node_ids))
        request = step.as_effect()
        self.assertTrue(request.intent.json_response)
        predicate = request.intent.success_pred
        self.assertTrue(predicate(StubResponse(202, {}), None))
        self.assertFalse(predicate(StubResponse(200, {}), None))

    def test_remove_nodes_from_clb_retry(self):
        """
        :obj:`RemoveNodesFromCLB`, on receiving a 400, parses out the nodes
        that are no longer on the load balancer, and retries the bulk delete
        with those nodes removed.

        TODO: this has been left in as a regression test - this can probably be
        removed the next time it's touched, as this functionality happens
        in cloud_client now and there is a similar test there.
        """
        lb_id = "12345"
        node_ids = [str(i) for i in range(5)]
        error_body = {
            "validationErrors": {
                "messages": [
                    "Node ids 1,2,3 are not a part of your loadbalancer"
                ]
            },
            "message": "Validation Failure",
            "code": 400,
            "details": "The object is not valid"
        }

        expected_req = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'DELETE',
            'loadbalancers/12345/nodes',
            params={'id': transform_eq(sorted, node_ids)},
            success_pred=ANY,
            json_response=True).intent
        expected_req2 = service_request(
            ServiceType.CLOUD_LOAD_BALANCERS,
            'DELETE',
            'loadbalancers/12345/nodes',
            params={'id': transform_eq(sorted, ['0', '4'])},
            success_pred=ANY,
            json_response=True).intent

        step = RemoveNodesFromCLB(lb_id=lb_id, node_ids=pset(node_ids))

        seq = [
            (expected_req,
             lambda i: raise_(APIError(400, json.dumps(error_body)))),
            (expected_req2, lambda i: stub_pure_response('', 202)),
        ]
        r = perform_sequence(seq, step.as_effect())
        self.assertEqual(r, (StepResult.SUCCESS, []))

    def test_remove_nodes_from_clb_non_terminal_failures_to_retry(self):
        """
        :obj:`RemoveNodesFromCLB` retries if the CLB is temporarily locked,
        or if the request was rate-limited, or if there was an API error and
        the error is unknown but not a 4xx.
        """
        non_terminals = (CLBImmutableError(lb_id=u"12345"),
                         CLBRateLimitError(lb_id=u"12345"),
                         APIError(code=500, body="oops!"),
                         TypeError("You did something wrong in your code."))
        eff = RemoveNodesFromCLB(lb_id='12345',
                                 node_ids=pset(['1', '2'])).as_effect()

        for exc in non_terminals:
            seq = SequenceDispatcher([(eff.intent, lambda i: raise_(exc))])
            with seq.consume():
                self.assertEquals(
                    sync_perform(seq, eff),
                    (StepResult.RETRY, [ErrorReason.Exception(
                        matches(ContainsAll([type(exc), exc])))]))

    def test_remove_nodes_from_clb_terminal_failures(self):
        """
        :obj:`AddNodesToCLB` fails if there are any 4xx errors, then
        the error is propagated up and the result is a failure.
        """
        terminals = (APIError(code=403, body="You're out of luck."),
                     APIError(code=422, body="Oh look another 422."))
        eff = RemoveNodesFromCLB(lb_id='12345',
                                 node_ids=pset(['1', '2'])).as_effect()

        for exc in terminals:
            seq = SequenceDispatcher([(eff.intent, lambda i: raise_(exc))])
            with seq.consume():
                self.assertEquals(
                    sync_perform(seq, eff),
                    (StepResult.FAILURE, [ErrorReason.Exception(
                        matches(ContainsAll([type(exc), exc])))]))

    def test_remove_nodes_from_clb_success_failures(self):
        """
        :obj:`AddNodesToCLB` succeeds if the CLB is not in existence (has been
        deleted or is not found).
        """
        successes = [CLBNotFoundError(lb_id=u'12345'),
                     CLBDeletedError(lb_id=u'12345'),
                     NoSuchCLBError(lb_id=u'12345')]
        eff = RemoveNodesFromCLB(lb_id='12345',
                                 node_ids=pset(['1', '2'])).as_effect()

        for exc in successes:
            seq = SequenceDispatcher([(eff.intent, lambda i: raise_(exc))])
            with seq.consume():
                self.assertEquals(sync_perform(seq, eff),
                                  (StepResult.SUCCESS, []))

    def _generic_bulk_rcv3_step_test(self, step_class, expected_method,
                                     exp_step_result):
        """
        A generic test for bulk RCv3 steps.

        :param step_class: The step class under test.
        :param str method: The expected HTTP method of the request.
        """
        lb_node_pairs = pset([
            ("lb-1", "node-a"),
            ("lb-1", "node-b"),
            ("lb-1", "node-c"),
            ("lb-1", "node-d"),
            ("lb-2", "node-a"),
            ("lb-2", "node-b"),
            ("lb-3", "node-c"),
            ("lb-3", "node-d")
        ])
        step = step_class(lb_node_pairs=lb_node_pairs)
        request = step.as_effect()
        self.assertEqual(request.intent.service_type,
                         ServiceType.RACKCONNECT_V3)
        self.assertEqual(request.intent.method, expected_method)

        success_pred = request.intent.success_pred
        if request.intent.method == "POST":
            self.assertEqual(success_pred, has_code(201, 409))
            success_code = 201
        else:
            self.assertEqual(success_pred, has_code(204, 409))
            success_code = 204

        self.assertEqual(request.intent.url, "load_balancer_pools/nodes")
        self.assertEqual(request.intent.headers, None)

        expected_data = [
            {'load_balancer_pool': {'id': 'lb-1'},
             'cloud_server': {'id': 'node-a'}},
            {'load_balancer_pool': {'id': 'lb-1'},
             'cloud_server': {'id': 'node-b'}},
            {'load_balancer_pool': {'id': 'lb-1'},
             'cloud_server': {'id': 'node-c'}},
            {'load_balancer_pool': {'id': 'lb-1'},
             'cloud_server': {'id': 'node-d'}},
            {'load_balancer_pool': {'id': 'lb-2'},
             'cloud_server': {'id': 'node-a'}},
            {'load_balancer_pool': {'id': 'lb-2'},
             'cloud_server': {'id': 'node-b'}},
            {'load_balancer_pool': {'id': 'lb-3'},
             'cloud_server': {'id': 'node-c'}},
            {'load_balancer_pool': {'id': 'lb-3'},
             'cloud_server': {'id': 'node-d'}}
        ]

        def key_fn(e):
            return (e["load_balancer_pool"]["id"], e["cloud_server"]["id"])

        request_data = sorted(request.intent.data, key=key_fn)
        self.assertEqual(request_data, expected_data)

        # Ensure that op is logged and same result is returned
        eff = resolve_effect(request, (StubResponse(success_code, {}), {}))
        self.assertEqual(eff.intent, log_intent('request-rcv3-bulk', {}))
        self.assertEqual(
            resolve_effect(eff, None), (exp_step_result, ANY))

    def test_add_nodes_to_rcv3_load_balancers(self):
        """
        :obj:`BulkAddToRCv3.as_effect` produces a request for
        adding any combination of nodes to any combination of RCv3 load
        balancers.
        """
        self._generic_bulk_rcv3_step_test(BulkAddToRCv3, "POST",
                                          StepResult.RETRY)

    def test_remove_nodes_from_rcv3_load_balancers(self):
        """
        :obj:`BulkRemoveFromRCv3.as_effect` produces a request
        for removing any combination of nodes from any combination of RCv3
        load balancers.
        """
        self._generic_bulk_rcv3_step_test(BulkRemoveFromRCv3, "DELETE",
                                          StepResult.SUCCESS)


_RCV3_TEST_DATA = {
    _RCV3_NODE_NOT_A_MEMBER_PATTERN: [
        ('Node d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2 is not a member of '
         'Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2',
         {'lb_id': 'd95ae0c4-6ab8-4873-b82f-f8433840cff2',
          'node_id': 'd6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2'}),
        ('Node D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 is not a member of '
         'Load Balancer Pool D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
         {'lb_id': 'D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
          'node_id': 'D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2'})
    ],
    _RCV3_NODE_ALREADY_A_MEMBER_PATTERN: [
        ('Cloud Server d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2 is already '
         'a member of Load Balancer Pool '
         'd95ae0c4-6ab8-4873-b82f-f8433840cff2',
         {'lb_id': 'd95ae0c4-6ab8-4873-b82f-f8433840cff2',
          'node_id': 'd6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2'}),
        ('Cloud Server D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 is already '
         'a member of Load Balancer Pool '
         'D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
         {'lb_id': 'D95AE0C4-6AB8-4873-B82F-F8433840CFF2',
          'node_id': 'D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2'})
    ],
    _RCV3_LB_INACTIVE_PATTERN: [
        ('Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2 is '
         'not in an ACTIVE state',
         {"lb_id": "d95ae0c4-6ab8-4873-b82f-f8433840cff2"}),
        ('Load Balancer Pool D95AE0C4-6AB8-4873-B82F-F8433840CFF2 is '
         'not in an ACTIVE state',
         {"lb_id": "D95AE0C4-6AB8-4873-B82F-F8433840CFF2"})
    ],
    _RCV3_LB_DOESNT_EXIST_PATTERN: [
        ("Load Balancer Pool d95ae0c4-6ab8-4873-b82f-f8433840cff2 does "
         "not exist",
         {"lb_id": "d95ae0c4-6ab8-4873-b82f-f8433840cff2"}),
        ("Load Balancer Pool D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2 does "
         "not exist",
         {"lb_id": "D6D3AA7C-DFA5-4E61-96EE-1D54AC1075D2"})
    ]
}


class RCv3RegexTests(SynchronousTestCase):
    """
    Tests for the RCv3 error parsing regexes.
    """
    def _regex_test(self, test_pattern):
        """A generic regex test.

        Asserts that the given test pattern has test data, matches all
        of its test data, and that it does not match all of the test
        data for all of the other patterns.
        """
        self.assertIn(test_pattern, _RCV3_TEST_DATA)
        for pattern, test_data in _RCV3_TEST_DATA.iteritems():
            if pattern is not test_pattern:
                for message, _ in test_data:
                    self.assertIdentical(test_pattern.match(message), None)
            else:
                for message, expected_group_dict in test_data:
                    res = pattern.match(message)
                    self.assertNotIdentical(res, None)
                    self.assertEqual(res.groupdict(), expected_group_dict)

    def test_node_not_a_member_regex(self):
        """
        The regex for parsing messages saying the node isn't part of the
        load balancer parses those messages. It rejects other
        messages.
        """
        self._regex_test(_RCV3_NODE_NOT_A_MEMBER_PATTERN)

    def test_node_already_a_member_regex(self):
        """
        The regex for parsing messages saying the node is already part of
        the load balancer parses those messages. It rejects other
        messages.
        """
        self._regex_test(_RCV3_NODE_ALREADY_A_MEMBER_PATTERN)

    def test_lb_inactive_regex(self):
        """
        The regex for parsing messages saying the load balancer is
        inactive parses those messages. It rejects other messages.
        """
        self._regex_test(_RCV3_LB_INACTIVE_PATTERN)

    def test_no_such_lb_message(self):
        """
        The regex for parsing messages saying the load balancer doesn't
        exist, parses those messages. It rejects other messages.
        """
        self._regex_test(_RCV3_LB_DOESNT_EXIST_PATTERN)


class RCv3CheckBulkAddTests(SynchronousTestCase):
    """
    Tests for :func:`_rcv3_check_bulk_add`.
    """
    def test_good_response(self):
        """
        If the response code indicates success, the step returns a RETRY so
        that another convergence cycle can be done to update the active server
        list.
        """
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        pairs = [(lb_a_id, node_a_id), (lb_b_id, node_b_id)]

        resp = StubResponse(201, {})
        body = [{"cloud_server": {"id": node_id},
                 "load_balancer_pool": {"id": lb_id}}
                for (lb_id, node_id) in pairs]
        res = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            res,
            (StepResult.RETRY,
             [ErrorReason.String(
              'must re-gather after adding to LB in order to update the '
              'active cache')]))

    def test_try_again(self):
        """
        If a node is already on the load balancer, returns RETRY
        """
        # This little piggy is already on the load balancer
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        # This little piggy is going to be added to this load balancer
        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        body = {"errors":
                ["Cloud Server {node_id} is already a member of Load "
                 "Balancer Pool {lb_id}"
                 .format(node_id=node_a_id, lb_id=lb_a_id)]}

        self.assertEqual(
            _rcv3_check_bulk_add(
                [(lb_a_id, node_a_id),
                (lb_b_id, node_b_id)],
                (StubResponse(409, {}), body)),
            (StepResult.RETRY,
             [ErrorReason.String(reason="Bulk addition partially succeeded")]))

    def test_node_already_a_member(self):
        """
        If all nodes were already member of the load balancers we were
        trying to add them to, the request is successful.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        pairs = [(lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Cloud Server {node_id} is already a member of Load "
            "Balancer Pool {lb_id}".format(node_id=node_id, lb_id=lb_id)]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            result,
            (StepResult.RETRY,
             [ErrorReason.String(
                 'must re-gather after adding to LB in order to '
                 'update the active cache')]))

    def test_lb_inactive(self):
        """
        If one of the LBs we tried to attach one or more nodes to is
        inactive, the request fails.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        pairs = [(lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Load Balancer Pool {lb_id} is not in an ACTIVE state"
            .format(lb_id=lb_id)]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            result,
            (StepResult.FAILURE,
             ["RCv3 LB {lb_id} was inactive".format(lb_id=lb_id)]))

    def test_multiple_lbs_inactive(self):
        """
        If multiple LBs we tried to attach one or more nodes to is
        inactive, the request fails, and all of the inactive LBs are
        reported.

        By logging as much of the failure as we can see, we will
        hopefully produce better audit logs.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_1_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        lb_2_id = 'fb32470f-6ebe-44a9-9360-3f48c9ac768c'
        pairs = [(lb_1_id, node_id), (lb_2_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Load Balancer Pool {lb_id} is not in an ACTIVE state"
            .format(lb_id=lb_id) for lb_id in [lb_1_id, lb_2_id]]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            result,
            (StepResult.FAILURE,
             ["RCv3 LB {lb_id} was inactive".format(lb_id=lb_id)
              for lb_id in [lb_1_id, lb_2_id]]))

    def test_lb_does_not_exist(self):
        """
        If one of the LBs we tried to attach one or more nodes to does not
        exist, the request fails.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        pairs = [(lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Load Balancer Pool {lb_id} does not exist"
            .format(lb_id=lb_id)]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            result,
            (StepResult.FAILURE,
             ["RCv3 LB {lb_id} does not exist".format(lb_id=lb_id)]))

    def test_multiple_lbs_do_not_exist(self):
        """
        If multiple LBs we tried to attach one or more nodes to do not
        exist, the request fails, and all of the nonexistent LBs are
        reported.

        By logging as much of the failure as we can see, we will
        hopefully produce better audit logs.
        """
        node_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_1_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'
        lb_2_id = 'fb32470f-6ebe-44a9-9360-3f48c9ac768c'
        pairs = [(lb_1_id, node_id), (lb_2_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Load Balancer Pool {lb_id} does not exist"
            .format(lb_id=lb_id) for lb_id in [lb_1_id, lb_2_id]]}
        result = _rcv3_check_bulk_add(pairs, (resp, body))
        self.assertEqual(
            result,
            (StepResult.FAILURE,
             ["RCv3 LB {lb_id} does not exist".format(lb_id=lb_id)
              for lb_id in [lb_1_id, lb_2_id]]))


class RCv3CheckBulkDeleteTests(SynchronousTestCase):
    """
    Tests for :func:`_rcv3_check_bulk_delete`.
    """
    def test_good_response(self):
        """
        If the response code indicates success, the response was successful.
        """
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        pairs = [(lb_a_id, node_a_id), (lb_b_id, node_b_id)]

        resp = StubResponse(204, {})
        body = [{"cloud_server": {"id": node_id},
                 "load_balancer_pool": {"id": lb_id}}
                for (lb_id, node_id) in pairs]
        res = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertEqual(res, (StepResult.SUCCESS, []))

    def test_try_again(self):
        """
        If a node was already removed (or maybe was never part of the load
        balancer pool to begin with), or some load balancer was
        inactive, or one of the load balancers doesn't exist, returns
        an effect that removes the remaining load balancer pairs.
        """
        # This little piggy isn't even on this load balancer.
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        # This little piggy is going to be removed from this load balancer.
        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        # This little piggy isn't active!
        node_c_id = '08944038-80ba-4ae1-a188-c827444e02e2'
        lb_c_id = '150895a5-1aa7-45b7-b7a4-98b9c282f800'

        # This isn't even a little piggy!
        node_d_id = 'bc1e94c3-0c88-4828-9e93-d42259280987'
        lb_d_id = 'de52879e-1f84-4ecd-8988-91dfdc99570d'

        body = {"errors":
                ["Node {node_id} is not a member of Load Balancer "
                 "Pool {lb_id}".format(node_id=node_a_id, lb_id=lb_a_id),
                 "Load Balancer Pool {lb_id} is not in an ACTIVE state"
                 .format(lb_id=lb_c_id),
                 "Load Balancer Pool {lb_id} does not exist"
                 .format(lb_id=lb_d_id)]}

        self.assertEqual(
            _rcv3_check_bulk_delete(
                [(lb_a_id, node_a_id),
                (lb_b_id, node_b_id),
                (lb_c_id, node_c_id),
                (lb_d_id, node_d_id)],
                (StubResponse(409, {}), body)),
            (StepResult.RETRY,
             [ErrorReason.String("Bulk removal partially successful")]))

    def test_nothing_to_retry(self):
        """
        If there are no further pairs to try and remove, the request was
        successful.

        This is similar to other tests, except that it tests the
        combination of all of them, even if there are several (load
        balancer, node) pairs for each reason.
        """
        node_a_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_a_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        node_b_id = "d6d3aa7c-dfa5-4e61-96ee-1d54ac1075d2"
        lb_b_id = 'd95ae0c4-6ab8-4873-b82f-f8433840cff2'

        node_c_id = '08944038-80ba-4ae1-a188-c827444e02e2'
        lb_c_id = '150895a5-1aa7-45b7-b7a4-98b9c282f800'

        node_d_id = 'bc1e94c3-0c88-4828-9e93-d42259280987'
        lb_d_id = 'de52879e-1f84-4ecd-8988-91dfdc99570d'

        not_a_member_pairs = [(lb_a_id, node_a_id), (lb_b_id, node_b_id)]
        inactive_pairs = [(lb_c_id, node_c_id)]
        nonexistent_lb_pairs = [(lb_d_id, node_d_id)]
        all_pairs = not_a_member_pairs + inactive_pairs + nonexistent_lb_pairs

        resp = StubResponse(409, {})
        body = {"errors":
                ["Node {node_id} is not a member of Load Balancer "
                 "Pool {lb_id}".format(node_id=node_id, lb_id=lb_id)
                 for (lb_id, node_id) in not_a_member_pairs] +
                ["Load Balancer Pool {} is not in an ACTIVE state"
                 .format(lb_id) for (lb_id, _node_id)
                 in inactive_pairs] +
                ["Load Balancer Pool {} does not exist"
                 .format(lb_id) for (lb_id, _node_id)
                 in nonexistent_lb_pairs]}
        result = _rcv3_check_bulk_delete(all_pairs, (resp, body))
        self.assertEqual(result, (StepResult.SUCCESS, []))

    def test_inactive_lb(self):
        """
        If the load balancer pool is inactive, the response was successful.
        """
        node_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        inactive_lb_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'
        pairs = [(inactive_lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": ["Load Balancer Pool {} is not in an ACTIVE state"
                           .format(inactive_lb_id)]}
        result = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertEqual(result, (StepResult.SUCCESS, []))

    def test_lb_does_not_exist(self):
        """
        If the load balancer doesn't even exist, the delete was successful.
        """
        node_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        nonexistent_lb_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'

        pairs = [(nonexistent_lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": ["Load Balancer Pool {} does not exist"
                           .format(nonexistent_lb_id)]}
        result = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertEqual(result, (StepResult.SUCCESS, []))

    def test_node_not_a_member(self):
        """
        If the nodes are already not member of the load balancer pools
        they're being removed from, the response was successful.
        """
        node_id = '825b8c72-9951-4aff-9cd8-fa3ca5551c90'
        lb_id = '2b0e17b6-0429-4056-b86c-e670ad5de853'
        pairs = [(lb_id, node_id)]

        resp = StubResponse(409, {})
        body = {"errors": [
            "Node {node_id} is not a member of Load Balancer "
            "Pool {lb_id}".format(node_id=node_id, lb_id=lb_id)]}
        result = _rcv3_check_bulk_delete(pairs, (resp, body))
        self.assertEqual(result, (StepResult.SUCCESS, []))


class ConvergeLaterTests(SynchronousTestCase):
    """
    Tests for :func:`ConvergeLater`
    """

    def test_returns_retry(self):
        """
        `ConvergeLater.as_effect` returns effect with RETRY
        """
        eff = ConvergeLater(reasons=['building']).as_effect()
        self.assertEqual(
            sync_perform(base_dispatcher, eff),
            (StepResult.RETRY, ['building']))


class FailConvergenceTests(SynchronousTestCase):
    """Tests for FailConvergence."""

    def test_returns_failure(self):
        """`FailConvergence.as_effect` returns effect with FAILURE."""
        eff = FailConvergence(reasons=['fail reason']).as_effect()
        self.assertEqual(sync_perform(base_dispatcher, eff),
                         (StepResult.FAILURE, ['fail reason']))


class CreateStackTests(SynchronousTestCase):
    """Tests for CreateStack."""

    def test_normal_use(self):
        """Tests normal usage."""

        stack_config = pmap({'stack_name': 'baz', 'foo': 'bar'})
        new_stack_config = pmap({'stack_name': 'baz_foo', 'foo': 'bar'})

        self.create = CreateStack(stack_config)
        self.seq = [
            (Func(uuid4), lambda _: 'foo'),
            (create_stack(thaw(new_stack_config)).intent,
             lambda _: (StubResponse(200, {}), {'stack': {}})),
            (Log('request-create-stack', ANY), lambda _: None)
        ]

        reason = 'Waiting for stack to create'
        result = perform_sequence(self.seq, self.create.as_effect())
        self.assertEqual(result,
                         (StepResult.RETRY, [ErrorReason.String(reason)]))


class CheckStackTests(SynchronousTestCase):
    """Tests for CheckStack."""
    def setUp(self):
        self.stack = stack(id='some_id', name='some_name')
        self.check_call = check_stack(stack_name=self.stack.name,
                                      stack_id=self.stack.id)

    def test_normal_use(self):
        """Tests normal usage."""
        self.assertEqual(CheckStack(stack=self.stack).as_effect().intent,
                         self.check_call.intent)

    def test_ensure_retry(self):
        """Tests that retry will be returned."""
        seq = [
            (self.check_call.intent, lambda _: (StubResponse(204, ''), None)),
            (Log('request-check-stack', ANY), lambda _: None)
        ]
        reason = 'Waiting for stack check to complete'
        result = perform_sequence(seq, CheckStack(self.stack).as_effect())
        self.assertEqual(result,
                         (StepResult.RETRY, [ErrorReason.String(reason)]))


class UpdateStackTests(SynchronousTestCase):
    """Tests for UpdateStack."""
    def setUp(self):
        self.config = pmap({'foo': 'bar', 'stack_name': 'to_be_removed'})
        self.config_after = {'foo': 'bar'}
        self.stack = stack(id='foo_id', name='foo_name')
        self.update_call = update_stack(stack_name=self.stack.name,
                                        stack_id=self.stack.id,
                                        stack_args=self.config_after)

    def test_normal_use(self):
        """Tests normal usage."""
        update = UpdateStack(stack=self.stack, stack_config=self.config)
        self.assertEqual(update.as_effect().intent,
                         self.update_call.intent)

    def test_retry_default(self):
        """Tests correct behavior when retry is not specified."""
        seq = [
            (self.update_call.intent, lambda _: (StubResponse(202, ''), None)),
            (Log('request-update-stack', ANY), lambda _: None)
        ]
        update = UpdateStack(stack=self.stack, stack_config=self.config)
        reason = 'Waiting for stack to update'
        result = perform_sequence(seq, update.as_effect())
        self.assertEqual(result,
                         (StepResult.RETRY, [ErrorReason.String(reason)]))

    def test_retry_false(self):
        """Tests correct behavior when retry is passed as false."""
        seq = [
            (self.update_call.intent, lambda _: (StubResponse(202, ''), None)),
            (Log('request-update-stack', ANY), lambda _: None)
        ]
        update = UpdateStack(stack=self.stack, stack_config=self.config,
                             retry=False)
        result = perform_sequence(seq, update.as_effect())
        self.assertEqual(result, (StepResult.SUCCESS, []))


class DeleteStackTests(SynchronousTestCase):
    """Tests for DeleteStack."""

    def test_normal_use(self):
        """Tests normal usage."""
        foo_stack = stack(id='foo', name='bar')
        delete = DeleteStack(foo_stack)
        self.assertEqual(delete.as_effect().intent,
                         delete_stack(stack_id='foo', stack_name='bar').intent)

    def test_ensure_retry(self):
        """Tests that retry will be returned."""
        seq = [
            (delete_stack(stack_id='foo', stack_name='bar').intent,
             lambda _: (StubResponse(204, ''), None)),
            (Log('request-delete-stack', ANY), lambda _: None)
        ]
        foo_stack = stack(id='foo', name='bar')
        delete = DeleteStack(foo_stack)
        reason = ('Waiting for stack to delete')
        result = perform_sequence(seq, delete.as_effect())
        self.assertEqual(result,
                         (StepResult.RETRY, [ErrorReason.String(reason)]))
