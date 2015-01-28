import json
import treq

from twisted.internet import defer, reactor
from twisted.trial import unittest

from otter import auth


username = 'sfalvo'
password = 'Ahshe1aelep7ooth,'


def dumpID(id):
    print "ID is ", id


def collectToken(js):
    id = js["access"]["token"]["id"]
    return id


class TestSpike(unittest.TestCase):
    def test_authentication_2(self):
        d = auth.authenticate_user(
            'https://identity.api.rackspacecloud.com/v2.0',
            username, password
        )
        d.addCallback(collectToken)
        d.addCallback(dumpID)
        return d

#     def test_authentication_1(self):
#         payload = json.dumps(
#             {"auth": {
#                 "passwordCredentials": {
#                     "username": username,
#                     "password": password
#                 }
#             }}
#         )
# 
#         def start():
#             return (
#                 treq.post(
#                     "https://identity.api.rackspacecloud.com/v2.0/tokens",
#                     data=payload,
#                     headers={
#                         "Content-Type": "application/json",
#                         "Accept": "application/json",
#                     },
#                 ).addCallback(assertResultCode)
#                 .addCallback(treq.json_content)
#                 .addCallback(collectToken)
#             )
# 
#         def assertResultCode(r):
#             self.assertEqual(r.code, 200)
#             return r
# 
#         return start().addCallback(dumpID)
# 
