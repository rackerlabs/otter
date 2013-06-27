

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

There are three components to Autoscale

- The Scaling Group Configuration
- The Scaling Group's Launch Configuration
- The Scaling Group's Policies
Autoscale Groups at a minimum require the Group Configuration, and a Launch Configuration. Policies are only required to make the group change.

The Group Configuration
-----------------------
This configuration specifies the basic elements of the config. Name, how many severs.

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

This will give you the basic steps to create an Autoscaling group. We recommend using http://docs.autoscale.apiary.io/ to generate CURL commands if you want to follow along in your environment.

Authentication
--------------

You will need to generate an auth token and then send it as 'X-Auth-token' header along with all the requests to authenticate yourself.

.. code-block:: bash

    POST https://identity.api.rackspacecloud.com/v2.0/tokens

You can request a token by providing your username and your API key.

.. code-block:: bash

 curl -X POST https://identity.api.rackspacecloud.com/v2.0/tokens -d '{ "auth":{ "RAX-KSKEY:apiKeyCredentials":{ "username":"theUserName", "apiKey":"00a00000a000a0000000a000a00aaa0a" } } }' -H "Content-type: application/json" | python -mjson.tool

You can request a token by providing your username and your password.

.. code-block:: bash

  curl -X POST https://identity.api.rackspacecloud.com/v2.0/tokens -d '{"auth":{"passwordCredentials":{"username":"theUserName","password":"thePassword"}}}' -H "Content-type: application/json" | python -mjson.tool

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
  $ curl -X GET -H "Content-Type: application/json" -H "X-Auth-token: {auth-token}" https://{region}.autoscale.api.rackspacecloud.com/v1.0/{tenant-id}/groups/ | python -mjson.tool

Step One - Save an Image
------------------------

First, boot a Rackspace Cloud Server, and customize it so that it can process requests. For example, if you're building a webhead autoscaling group, configure Apache2 to start on launch, and serve the files you need.

When that is complete, save your image, and record the imageID.

.. code-block:: bash

  $ curl -X GET -H "Content-Type: application/json" -H "X-Auth-token: {auth-token}" https://ord.servers.api.rackspacecloud.com/v2/{Tenant-id}/images?type=SNAPSHOT | python -mjson.tool

Step Two - Create the Group
---------------------------

Create a Scaling Group by submitting a POST request containing an edited version of these data. 


``POST https://autoscale.api.rackspacecloud.com/v1.0/[TenantID]/groups/``

.. code-block:: bash

    {
        "groupConfiguration": {
            "name": "myFirstAutoscalingGroup",
            "cooldown": 60,
            "minEntities": 1,
            "maxEntities": 10,
        },
        "launchConfiguration": {
            "type": "launch_server",
            "args": {
                "server": {
                    "flavorRef": 3,
                    "name": "webhead",
                    "imageRef": "[Your ImageID Here]",
                },
                "loadBalancers": [
                    {
                        "loadBalancerId": [Your LoadBalancerID],
                        "port": 8080
                    }
                ]
            }
        },
        "scalingPolicies": []
    }


This will create your scaling group, spin up the minimum number of servers, and then attach them to the load balancer you specified. To modify the group, you will need to create policies.

Step Three - Policies
---------------------
Scaling Down is not yet implemented. You must manually remove your servers via Nova.
Create scaling policies by sending POST requests


``POST https://autoscale.api.rackspacecloud.com/v1.0/[TenantID]/groups/[GroupID]/policies/``

.. code-block:: bash

  [
      {
          "name": "scale up by one server",
          "change": 1,
          "cooldown": 150,
          "type": "webhook"
      },
      {
          "name": "scale down by 5.5 percent",
          "changePercent": -5.5,
          "cooldown": 6,
          "type": "webhook"
      }
  ]

Step Four - Webhooks
--------------------

Now that you've created the policy, let's create a few webhooks.

``POST https://autoscale.api.rackspacecloud.com/v1.0/{tenantId}/groups/{groupId}/policies/{policyId}/webhooks``

.. code-block:: bash

  [
      {
          "name": "alice",
          "metadata": {
              "notes": "this is for Alice"
          }
      }
  ]

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
                      "href": ".../execute/1/{capability_hash1}/,
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
                      "href": ".../execute/1/{capability_hash2}/,
                      "rel": "capability"
                  }
              ]
          }
      ]
  }

Step Five - Executing a Scaling Policy
--------------------------------------

Find the execute URL in your Scaling Policy. If you want to activate that policy, POST against it.

``curl -X POST https://autoscale.api.rackspacecloud.com/v1.0/execute/1/{capability_hash}/ -v``

The policy will execute, and your group will transform. Do this the right way at the right time, you might just have a working environment!

An execution will always return "202, Accepted", even if it fails to scale because of an invalid configuration. This is done to prevent scraping hashes across the environment.

Step Six - Tearing it all down
------------------------------

Autoscaling groups will not delete unless all the servers are removed. To do this, upload a new config with minimum and maximum of zero.


``PUT /{tenantId}/groups/{groupId}/config``

.. code-block:: bash

  {
      "name": "workers",
      "cooldown": 60,
      "minEntities": 0,
      "maxEntities": 0,
      "metadata": {
          "firstkey": "this is a string",
          "secondkey": "1",
      }
  }


The autoscale group will start destroying all your servers. When they're gone, you can fire a DELETE command to the Group ID:

``DELETE /{tenantId}/groups/{groupId}``