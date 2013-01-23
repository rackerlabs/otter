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
GET       ../:id/policies                       List basic info of all scaling policies
POST      ../:id/policies                       Create scaling policy
GET       ../:id/policies/:id                   Get details of a specific scaling policy, including webhook details
PUT       ../:id/policies/:id                   Update/Create details of a specific scaling policy
DELETE    ../:id/policies/:id                   Delete a specific scaling policy
GET       ../:id/policies/:id/webhook           List basic info for all webhooks under scaling policy
POST      ../:id/policies/:id/webhook           Create a new public webhook for Scaling Policy
GET       ../:id/policies/:id/webhook/:id       Get details of a specific webhook (name, URL, access details)
PUT       ../:id/policies/:id/webhook/:id       Update webhooks under scaling policy
DELETE    ../:id/policies/:id/webhook/:id       Delete a public webhook
GET       ../action/:hash                       Activate a public Autoscale endpoint
========= ===================================== ===========================================================================================
