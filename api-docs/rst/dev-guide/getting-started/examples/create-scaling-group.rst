.. _create-a-scaling-group:

Create a scaling group
~~~~~~~~~~~~~~~~~~~~~~
Now you are ready to create your first scaling group. For this
exercise, you will create a schedule-based scaling group that will
trigger a scaling event at 11 P.M. daily. The following example shows
how to create a schedule-based scaling group by submitting a
POST request using cURL.

.. code::

     {
        "launchConfiguration":{
           "args":{
              "loadBalancers":[
                 {
                    "port":80,
                    "loadBalancerId":237935
                 }
              ],
              "server":{
                 "name":"autoscale_server",
                 "imageRef":"7cf5ffc3-7b20-46fd-98e4-fefa9908d7e8",
                 "flavorRef":"performance1-2",
                 "OS-DCF:diskConfig":"AUTO",
                 "networks":[
                    {
                       "uuid":"11111111-1111-1111-1111-111111111111"
                    },
                    {
                       "uuid":"00000000-0000-0000-0000-000000000000"
                    }
                 ]
              }
           },
           "type":"launch_server"
        },
        "groupConfiguration":{
           "maxEntities":10,
           "cooldown":360,
           "name":"testscalinggroup",
           "minEntities":0
        },
        "scalingPolicies":[
           {
              "cooldown":0,
              "name":"scale up by 1",
              "change":1,
              "type":"schedule",
              "args":{
                 "cron":"23 * * * *"
              }
           }
        ]
     }

If the POST request is successful, the response data will be returned in
JSON format as shown in the following example:

.. code::

     {
        "group":{
           "groupConfiguration":{
              "cooldown":360,
              "maxEntities":10,
              "metadata":{

              },
              "minEntities":0,
              "name":"testscalinggroup"
           },
           "id":"48692442-2dbe-4311-955e-bc29f02ae311",
           "launchConfiguration":{
              "args":{
                 "loadBalancers":[
                    {
                       "loadBalancerId":237935,
                       "port":80
                    }
                 ],
                 "server":{
                    "OS-DCF:diskConfig":"AUTO",
                    "flavorRef":"performance1-2",
                    "imageRef":"7cf5ffc3-7b20-46fd-98e4-fefa9908d7e8",
                    "name":"autoscale_server",
                    "networks":[
                       {
                          "uuid":"11111111-1111-1111-1111-111111111111"
                       },
                       {
                          "uuid":"00000000-0000-0000-0000-000000000000"
                       }
                    ]
                 }
              },
              "type":"launch_server"
           },
           "links":[
              {
                 "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/829409/groups/48692442-2dbe-4311-955e-bc29f02ae311/",
                 "rel":"self"
              }
           ],
           "scalingPolicies":[
              {
                 "args":{
                    "cron":"23 * * * *"
                 },
                 "change":1,
                 "cooldown":0,
                 "id":"9fa63149-c93d-4116-8069-74d68f48fadc",
                 "links":[
                    {
                       "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/829409/groups/48692442-2dbe-4311-955e-bc29f02ae311/policies/9fa63149-c93d-4116-8069-74d68f48fadc/",
                       "rel":"self"
                    }
                 ],
                 "name":"scale up by 1",
                 "type":"schedule"
              }
           ],
           "scalingPolicies_links":[
              {
                 "href":"https://dfw.autoscale.api.rackspacecloud.com/v1.0/829409/groups/48692442-2dbe-4311-955e-bc29f02ae311/policies/",
                 "rel":"policies"
              }
           ],
           "state":{
              "active":[

              ],
              "activeCapacity":0,
              "desiredCapacity":0,
              "name":"testscalinggroup",
              "paused":false,
              "pendingCapacity":0
           }
        }
     }
