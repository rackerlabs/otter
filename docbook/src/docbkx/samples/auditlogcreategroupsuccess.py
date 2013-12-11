examples = [
            ("Creating a group successfully", [
                                               {
                                               "timestamp": "2013-01-01T00:00:01.000001Z",
                                               "_message": "Created a group.",
                                               "request_ip": "85.125.12.1",
                                               "user_id": "11111",
                                               "scaling_group_id": "10000000-0000-0000-0000-00000000001",
                                               "data": {
                                               "groupConfiguration": {
                                               "name": "new name", "cooldown": 5, "minEntities": 2
                                               },
                                               "launchConfiguration": {
                                               "type": "launch_server",
                                               "args": {
                                               "server": {
                                               "flavorRef": 2,
                                               "name": "web",
                                               "imageRef": "52415800-8b69-11e0-9b19-734f6f007777"
                                               }
                                               }
                                               },
                                               "scalingPolicies": [
                                                                   {
                                                                   "name": "scale up by 10",
                                                                   "change": 10,
                                                                   "cooldown": 5,
                                                                   "type": "webhook"
                                                                   }
                                                                   ]
                                               },
                                               "transaction_id": "00000000-0000-0000-0000-00000000001",
                                               "event_type": "request.group.create.ok",
                                               "event_status": "ok",
                                               "desired_capacity": 2,
                                               "pending_capacity": 0,
                                               "current_capacity": 0
                                               },
                                               {
                                               "timestamp": "2013-01-01T00:00:02.000001Z",
                                               "_message": "Starting two new servers to satisfy desired capacity",
                                               "scaling_group_id": "10000000-0000-0000-0000-00000000001",
                                               "parent_id": "00000000-0000-0000-0000-00000000001",
                                               "transaction_id": "00000000-0000-0000-0000-00000000002",
                                               "as_user_id": "10000",
                                               "event_type": "convergence.scale_up",
                                               "event_status": "ok",
                                               "desired_capacity": 2,
                                               "pending_capacity": 2,
                                               "current_capacity": 0,
                                               "convergence_delta": 2
                                               },
                                               {
                                               "timestamp": "2013-01-01T00:05:01.000001Z",
                                               "_message": "Server is Active",
                                               "scaling_group_id": "10000000-0000-0000-0000-00000000001",
                                               "parent_id": "00000000-0000-0000-0000-00000000002",
                                               "transaction_id": "00000000-0000-0000-0000-00000000003",
                                               "server_id": "11111111-0000-0000-0000-00000000001",
                                               "event_type": "server.active",
                                               "event_status": "ok"
                                               },
                                               {
                                               "timestamp": "2013-01-01T00:05:01.000001Z",
                                               "_message": "Server is Active",
                                               "scaling_group_id": "10000000-0000-0000-0000-00000000001",
                                               "parent_id": "00000000-0000-0000-0000-00000000002",
                                               "transaction_id": "00000000-0000-0000-0000-00000000004",
                                               "server_id": "11111111-0000-0000-0000-00000000002",
                                               "event_type": "server.active",
                                               "event_status": "ok"
                                               }
                                               ]),
 )