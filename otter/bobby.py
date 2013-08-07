"""
                  _A
                .'`"`'.
               /   , , \
              |   <\^/> |
              |  < (_) >|
              /===</V\>=\
             (.---._ _.-.)
              |/   a` a |
              (      _\ |
               \    __  ;
               |\   .  /
            _.'\ '----;'-.
        _.-'  O ;-.__.'\O `o.
       /o \      \/-.-\/|    \
      |    ;,     '.|\| /

This is the utility stuff for working with Bobby.

"""

import treq
import json

from otter.util.http import (append_segments, check_success,
                             wrap_request_error)

from otter.util.config import config_value


def create_policy(tenant_id, group_id, policy_id, check_template, alarm_template):
    """
    Create a policy
    """
    server_endpoint = config_value('bobby_endpoint')
    payload = {
        'alarmTemplate': alarm_template,
        'checkTemplate': check_template,
        'policyId': policy_id
    }
    d = treq.post(append_segments(server_endpoint, tenant_id, 'groups', group_id, 'policies'),
                  data=json.dumps(payload))
    d.addCallback(check_success, [201])
    d.addErrback(wrap_request_error, server_endpoint, 'create_policy')
    return d.addCallback(treq.json_content)


def create_server(tenant_id, group_id, server_id, entity_id):
    """
    Create a server
    """
    server_endpoint = config_value('bobby_endpoint')
    payload = {
        'serverId': server_id,
        'entityId': entity_id
    }
    d = treq.post(append_segments(server_endpoint, tenant_id, 'groups', group_id, 'servers'),
                  data=json.dumps(payload))
    d.addCallback(check_success, [201])
    d.addErrback(wrap_request_error, server_endpoint, 'create_server')
    return d.addCallback(treq.json_content)


def create_group(tenant_id, group_id):
    """ Create a group in bobby """
    server_endpoint = config_value('bobby_endpoint')
    payload = {
        'groupId': group_id,
        'notification': 'Damnit, Bobby',  # these shouldn't be passed to Bobby
        'notificationPlan': 'Damnit, Bobby'
    }
    d = treq.post(append_segments(server_endpoint, tenant_id, 'groups'),
                  data=json.dumps(payload))
    d.addCallback(check_success, [201])
    d.addErrback(wrap_request_error, server_endpoint, 'create_group')
    return d.addCallback(treq.json_content)
