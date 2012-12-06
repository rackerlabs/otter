====================
Endpoint APIs
====================

Base Endpoint   /:tenant_id/autoscaling/

========= =========================   ===========================================================================================
Method    Endpoint                    Details
========= =========================   ===========================================================================================
GET       ../                         List autoscaling groups
POST      ../                         Create autoscaling group
GET       ../:id                      List status of entities in autoscaling group
PUT       ../:id                      Update scaling group configuration details
GET       ../:id/details              List full details of scaling configuration, including launch configs and scaling policies
PUT       ../:id/details              Update full details of scaling configuration.
GET       ../:id/launch_config        List basic info of all launch configurations
POST      ../:id/launch_config        Create launch configuration
GET       ../:id/launch_config/:id    Get details of specific launch configuration
PUT       ../:id/launch_config/:id    Update details of a specific launch configuration
GET       ../:id/scaling_policy/      List basic info of all scaling policies
POST      ../:id/scaling_policy/      Create scaling policie
GET       ../:id/scaling_policy/:id   Get details of a specific scaling policy
PUT       ../:id/scaling_policy/:id   Update details of a specific scaling policy
========= =========================   ===========================================================================================

