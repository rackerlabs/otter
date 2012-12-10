====================
Endpoint APIs
====================

Base Endpoint   /:tenant_id/autoscaling/

========= ===================================== ===========================================================================================
Method    Endpoint                              Details
========= ===================================== ===========================================================================================
GET       ../                                   List autoscaling groups
POST      ../                                   Create autoscaling group
GET       ../:id                                List full details of scaling configuration, including launch configs and scaling policies
PUT       ../:id                                Update full details of scaling configuration
DELETE    ../:id                                Delete scaling group (when empty; reject when group has entities)
GET       ../:id/state                          List status of entities in autoscaling group
GET       ../:id/group_config                   List scaling group configuration details
PUT       ../:id/group_config                   Update/Create scaling group configuration details
GET       ../:id/launch_config                  List info of launch configuration
PUT       ../:id/launch_config                  Update/Create launch configuration
GET       ../:id/scaling_policy                 List basic info of all scaling policies
POST      ../:id/scaling_policy                 Create scaling policy
GET       ../:id/scaling_policy/:id             Get details of a specific scaling policy, including webhook details
PUT       ../:id/scaling_policy/:id             Update/Create details of a specific scaling policy
DELETE    ../:id/scaling_policy/:id             Delete a specific scaling policy
GET       ../:id/scaling_policy/:id/webhook     List basic info for all webhooks under scaling policy
PUT       ../:id/scaling_policy/:id/webhook     Bulk Update/Create all webhooks under scaling policy
POST      ../:id/scaling_policy/:id/webhook     Create a new public webhook for Scaling Policy
GET       ../:id/scaling_policy/:id/webhook/:id Get details of a specific webhook (name, URL, access details)
DELETE    ../:id/scaling_policy/:id/webhook/:id Delete a public webhook
GET       ../action/:hash                       Activate a public Autoscale Endpoint
========= ===================================== ===========================================================================================
