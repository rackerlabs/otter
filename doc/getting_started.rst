

***************
Getting Started
***************

Core Concepts
=============

Autoscale is an API based tool that enables you to scale your servers up and down in response to variation in load.

Autoscale functions by linking three services:

- Monitoring (such as Monitoring as a Service)
- Autoscale API
- Servers and Load Balancers

Basic Workflow
--------------

An autoscaling group is monitored by Rackspace Cloud Monitoring. When Monitoring triggers an alarm for high utilization within the autoscaling group, a webhook is triggered. The webhook stimulates the autoscale service which consults a policy in accordance with the webhook. The policy determines how many additional cloud servers should be added or removed in accordance with the alarm.

Alarms may trigger scaling up or scaling down. Currently scale down events always remove the oldest server in the group.

Cooldowns allow you to ensure that you don't scale up or down too fast. When a scaling policy is hit, both the scaling policy cooldown and the group cooldown start. Any additional requests to the group are discarded while the group cooldown is active. Any additional requests to the specific policy are discarded when the policy cooldown is active.

Autoscale does not configure anything within a server. It is up to you to make sure that your services are configured to function properly when the server is started. We recommend using something like Chef.

Example Use Case
----------------

Five servers are in an autoscaling group, with Rackspace Cloud Monitoring monitoring their CPU usage. Monitoring will trigger an alarm when CPU is at 90%. That alarm will trigger a webhook that Autoscale created previously. When that webhook is hit, autoscale receives the alert, and carries out a policy specific to that webhook. This policy says "When my webhook is hit, create five servers according to the launch configuration, and add them to the load balancer." Autoscale will then ensure those servers are stood up.

Autoscale can also work in the opposite direction. A policy can say "When my webhook is hit, scale down by five servers."


The Scaling Group
=================

There are three components to Autoscale:

- The Scaling Group Configuration
- The Scaling Group's Launch Configuration
- The Scaling Group's Policies

Autoscale Groups at a minimum require the Group Configuration, and a Launch Configuration. Policies are only required to make the group change.

The Group Configuration
-----------------------
This configuration specifies the basic elements of the config.

The Group Configuration contains:

- Group Name
- Group Cooldown (how long a group has to wait before you can scale again in seconds)
- Minimum and Maximum of entities allowed in the autoscaling Group.

The Launch Configuration
------------------------

This configuration specifies what to do when we want to create a new server. What image to boot, on what flavor, and which load balancer to connect it to.

The Launch Configuration Contains:

- Launch Configuration Type

  - Launch Server

    - Note: This is the only choice right now

- Server. Note: This is the same as a Cloud Server Configuration

  - name
  - flavor
  - imageRef

    - Note: This is the ID of the Cloud Server image you will boot

- Load Balancer

  - loadBalancerId
  - port


Scaling Policies
----------------
Scaling policies specify how to change the Autoscaling Group. There can be multiple scaling policies per group.

Scaling Policies Contain:

- Scaling Policy Name
- Change Value (incremental, or by percent)
- Policy Cooldown (in seconds)
- Execute Webhook (auto-generated)


Walking Through the Autoscale API
=================================

This will give you the basic steps to create an Autoscaling group. We recommend using http://docs.ord.autoscale.apiary.io/ to generate CURL commands if you want to follow along in your environment.

Authentication
--------------

You will need to generate an auth token and then send it as 'X-Auth-token' header along with all the requests to authenticate yourself.

Authentication Endpoint: ``https://identity.api.rackspacecloud.com/v2.0/tokens``

You can request a token by providing your username and your API key.

.. code-block:: bash

 curl --request POST -H "Content-type: application/json" \
    --data-binary '{
      "auth":{
        "RAX-KSKEY:apiKeyCredentials":{
          "username":"theUserName",
          "apiKey":"00a00000a000a0000000a000a00aaa0a"
        }
      }
   }' \
  https://identity.api.rackspacecloud.com/v2.0/tokens | python -mjson.tool

You can request a token by providing your username and your password.

.. code-block:: bash

  curl --request POST  -H "Content-type: application/json" \
   --data-binary '{
     "auth":{
       "passwordCredentials":{
         "username":"username",
         "password":"password"}
       }
     }' \
   https://identity.api.rackspacecloud.com/v2.0/tokens | python -mjson.tool

The response will be HUGE (sorry!) We've snipped the serviceCatalog bit for clarity.


.. code-block:: bash

  {
      "access": {
          "serviceCatalog": [
             ...
          ],
          "token": {
              "expires": "2012-04-13T13:15:00.000-05:00",
              "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
               "tenant": {
                  "id": "123456",
                  "name": "123456"
              }
          },
          "user": {
              "RAX-AUTH:defaultRegion": "DFW",
              "id": "161418",
              "name": "demoauthor",
              "roles": [
                  {
                      "description": "User Admin Role.",
                      "id": "3",
                      "name": "identity:user-admin"
                  }
              ]
          }
      }
  }

Note your token.id and your user.id. That token.tenant.id is your "tenantID" and you will need it to make requests to Autoscale.

If the auth token received is "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" and your tenantID is 123456 then this example request will list all groups you've created:

.. code-block:: bash

  $ curl -X GET -H "Content-Type: application/json" -H "X-Auth-token: {auth-token}" https://{region}.ord.autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/ | python -mjson.tool

Step One - Save an Image
------------------------

First, boot a Rackspace Cloud Server, and customize it so that it can process requests. For example, if you're building a webhead autoscaling group, configure Apache2 to start on launch, and serve the files you need.

When that is complete, save your image, and record the imageID.

.. code-block:: bash

  $ curl --request GET --header "Content-Type: application/json" \
   --header "X-Auth-token: {auth-token}" \
   https://ord.servers.api.rackspacecloud.com/v2/{Tenant-id}/images?type=SNAPSHOT \
   | python -mjson.tool

Step Two - Create the Group
---------------------------

Create a Scaling Group by submitting a POST request containing an edited version of these data. 


.. code-block:: bash

  POST https://ord.autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/

.. code-block:: bash

    curl --include --header "Accept: application/json" \
         --header "X-Auth-token: {auth-token}" \
         --request POST \
         --data-binary "{
        \"groupConfiguration\": {
            \"name\": \"workers\",
            \"cooldown\": 60,
            \"minEntities\": 5,
            \"maxEntities\": 100,
            \"metadata\": {
                \"firstkey\": \"this is a string\",
                \"secondkey\": \"1\"
            }
        },
        \"launchConfiguration\": {
            \"type\": \"launch_server\",
            \"args\": {
                \"server\": {
                    \"flavorRef\": 3,
                    \"name\": \"webhead\",
                    \"imageRef\": \"0d589460-f177-4b0f-81c1-8ab8903ac7d8\",
                    \"OS-DCF:diskConfig\": \"AUTO\",
                    \"metadata\": {
                        \"mykey\": \"myvalue\"
                    },
                    \"personality\": [
                        {
                            \"path\": \'/root/.ssh/authorized_keys\',
                            \"contents\": \"ssh-rsa AAAAB3Nza...LiPk== user@example.net\"
                        }
                    ],
                    \"networks\": [
                        {
                            \"uuid\": \"11111111-1111-1111-1111-111111111111\"
                        }
                    ],
                },
                \"loadBalancers\": [
                    {
                        \"loadBalancerId\": 2200,
                        \"port\": 8081
                    }
                ]
            }
        },
        \"scalingPolicies\": [
        ]
    }" \
         "https://ord.autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/"

This will create your scaling group, spin up the minimum number of servers, and then attach them to the load balancer you specified. To modify the group, you will need to create policies.

Step Three - Policies
---------------------

Create scaling policies by sending POST requests

.. code-block:: bash

  POST https://ord.autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/{groupId}/policies/

.. code-block:: bash

  curl --include --header "Accepts: application/json" \
       --header "X-Auth-token: {auth-token}" \
       --request POST \
       --data-binary "[
      {
          \"name\": \"scale up by one server\",
          \"change\": 1,
          \"cooldown\": 150,
          \"type\": \"webhook\"
      },
      {
          \"name\": \"scale down by 5.5 percent\",
          \"changePercent\": -5.5,
          \"cooldown\": 6,
          \"type\": \"webhook\"
      }
  ]" \
       "https://ord.autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/{groupId}/policies"

Step Four - Webhooks
--------------------

Now that you've created the policy, let's create a few webhooks.

.. code-block:: bash

  POST https://ord.autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/{groupId}/policies/{policyId}/webhooks


.. code-block:: bash

    curl --include --header "Accepts: application/json" \
         --header "X-Auth-token: {auth-token}" \
         --request POST \
         --data-binary "[
        {
            \"name\": \"alice\",
            \"metadata\": {
                \"notes\": \"this is for Alice\"
            }
        },
        {
            \"name\": \"bob\"
        }
    ]" \
         "https://ord.autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/{groupId}/policies/{policyId}/webhooks"

Will reply with:

.. code-block:: bash

  {
      "webhooks": [
          {
              "id":"{webhookId1}",
              "alice",
              "metadata": {
                  "notes": "this is for Alice"
              },
              "links": [
                  {
                      "href": ".../{groupId1}/policies/{policyId1}/webhooks/{webhookId1}/",
                      "rel": "self"
                  },
                  {
                      "href": ".../execute/1/{capabilityHash1}/",
                      "rel": "capability"
                  }
              ]
          },
          {
              "id":"{webhookId2}",
              "name": "bob",
              "metadata": {},
              "links": [
                  {
                      "href": ".../{groupId1}/policies/{policyId1}/webhooks/{webhookId2}/",
                      "rel": "self"
                  },
                  {
                      "href": ".../execute/1/{capabilityHash2}/",
                      "rel": "capability"
                  }
              ]
          }
      ]
  }

Step Five - Executing a Scaling Policy
--------------------------------------

You can excecute a scaling policy in two ways:

**Authenticated Scaling Policy Path**

Identify the path to the desired scaling policy, and append 'execute' to the path. To activate the policy POST against it.

.. code-block:: bash

  curl --include \
       --header "X-Auth-token: {auth-token}" \
       --request POST \
       "https://private-a6a2-autoscale.apiary.io/v1.0/{tenantId}/groups/{groupId}/policies/{policyId}/execute"

**Execute Capability URL**

Find the capability URL in your Scaling Policy Webhook. If you want to activate that policy, POST against it.

.. code-block:: bash

  curl --include \
     --header "X-Auth-token: {auth-token}" \
     --request POST \
     "https://ord.autoscale.api.rackspacecloud.com/v1.0/execute/{capabilityVersion}/{capabilityHash}/" -v

Note how authentication is not needed.

The policy will execute, and your group will transform. Do this the right way at the right time, you might just have a working environment!

An execution will always return ``202, Accepted``, even if it fails to scale because of an invalid configuration. This is done to prevent `information leakage <https://www.owasp.org/index.php/Information_Leakage>`_.

Step Six - Tearing it all down
------------------------------

Autoscaling groups can not be deleted while they have active servers. Upload a new config with minimum and maximum of zero to be able to delete a server.


.. code-block:: bash

  PUT /{tenantId}/groups/{groupId}/config

.. code-block:: bash

 curl --include --header "Accept: application/json" \
     --header "X-Auth-token: {auth-token}" \
     --request PUT \
     --data-binary "{
    \"name\": \"workers\",
    \"cooldown\": 60,
    \"minEntities\": 0,
    \"maxEntities\": 0,
    \"metadata\": {
        \"firstkey\": \"this is a string\",
        \"secondkey\": \"1\",
    }
  }" \
     "https://ord.autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/{groupId}/config"


The autoscale group will start destroying all your servers. Now you can fire a DELETE command to the Group ID. Take care that all your servers are deleted before deleting the group.

.. code-block:: bash

  curl --include \
     --header "X-Auth-token: {auth-token}" \
     --request DELETE \
     "https://ord.autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/{groupId}"