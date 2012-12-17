====================
Endpoint APIs
====================

Base Endpoint   /:tenant_id/groups/

========= ===================================== ===========================================================================================
Method    Endpoint                              Details
========= ===================================== ===========================================================================================
GET       ../                                   List autoscaling groups
POST      ../                                   Create autoscaling group
GET       ../:id                                List full details of scaling configuration, including launch configs and scaling policies
PUT       ../:id                                Update full details of scaling configuration
DELETE    ../:id                                Delete scaling group (when empty; reject when group has entities)
GET       ../:id/state                          List status of entities in autoscaling group
GET       ../:id/group                          List scaling group configuration details
PUT       ../:id/group                          Update/Create scaling group configuration details
GET       ../:id/launch                         List info of launch configuration
PUT       ../:id/launch                         Update/Create launch configuration
GET       ../:id/policy                         List basic info of all scaling policies
POST      ../:id/policy                         Create scaling policy
GET       ../:id/policy/:id                     Get details of a specific scaling policy, including webhook details
PUT       ../:id/policy/:id                     Update/Create details of a specific scaling policy
DELETE    ../:id/policy/:id                     Delete a specific scaling policy
GET       ../:id/policy/:id/webhook             List basic info for all webhooks under scaling policy
POST      ../:id/policy/:id/webhook             Create a new public webhook for Scaling Policy
GET       ../:id/policy/:id/webhook/:id         Get details of a specific webhook (name, URL, access details)
PUT       ../:id/policy/:id/webhook/:id         Update webhooks under scaling policy
DELETE    ../:id/policy/:id/webhook/:id         Delete a public webhook
GET       ../action/:hash                       Activate a public Autoscale endpoint
========= ===================================== ===========================================================================================
