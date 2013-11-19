"""
Creates an audit log index and loads mappings and sample documents into it
"""

from __future__ import print_function

examples = [
    ("Creating a group successfully", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Created a group.",
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
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
            "is_error": False,
            "desired_capacity": 2,
            "pending_capacity": 0,
            "current_capacity": 0
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": "Starting two new servers to satisfy desired capacity",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000002",
            "as_user_id": "10000",
            "event_type": "convergence.scale_up",
            "is_error": False,
            "desired_capacity": 2,
            "pending_capacity": 2,
            "current_capacity": 0,
            "convergence_delta": 2
        },
        {
            "timestamp": "2013-01-01T00:05:01.000001Z",
            "_message": "Server is Active",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000003",
            "server_id": "11111111-0000-0000-0000-00000000001",
            "event_type": "server.active",
            "is_error": False
        },
        {
            "timestamp": "2013-01-01T00:05:01.000001Z",
            "_message": "Server is Active",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000004",
            "server_id": "11111111-0000-0000-0000-00000000002",
            "event_type": "server.active",
            "is_error": False
        }
    ]),

    ("Creating a group unsuccessfully", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Failed to created a group - invalid launch config due to imageRef \"image\".",
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
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
                            "imageRef": "image"
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
            "event_type": "request.group.create.failure.invalid_launch_config",
            "is_error": False,
            "fault": {
                "code": 400,
                "message": "Invalid Launch Config...",
                "details": "Error Details..."
            }
        }
    ]),

    ("Executing a scaling policy successfully", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Execute scaling policy.",
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "policy_id": "20000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "event_type": "request.policy.execute.ok",
            "is_error": False,
            "desired_capacity": 4,
            "previous_desired_capacity": 2,
            "pending_capacity": 0,
            "current_capacity": 2
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": "Starting 2 new servers to satisfy desired capacity",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000002",
            "as_user_id": "10000",
            "event_type": "convergence.scale_up",
            "is_error": False,
            "desired_capacity": 4,
            "pending_capacity": 2,
            "current_capacity": 2,
            "convergence_delta": 2
        },
        {
            "timestamp": "2013-01-01T00:05:01.000001Z",
            "_message": "Server is Active",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000003",
            "server_id": "11111111-0000-0000-0000-00000000001",
            "event_type": "server.active",
            "is_error": False
        },
        {
            "timestamp": "2013-01-01T00:05:02.000001Z",
            "_message": "Server is Active",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000004",
            "server_id": "11111111-0000-0000-0000-00000000002",
            "event_type": "server.active",
            "is_error": False
        }
    ]),

    ("Executing a webhook successfully", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Execute webhook policy.",
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "policy_id": "20000000-0000-0000-0000-00000000001",
            "webhook_id": "30000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "event_type": "request.webhook.capability.execute.ok",
            "is_error": False,
            "desired_capacity": 4,
            "previous_desired_capacity": 2,
            "current_capacity": 2
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": "Starting 2 new servers to satisfy desired capacity",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000002",
            "as_user_id": "10000",
            "event_type": "convergence.scale_up",
            "is_error": False,
            "desired_capacity": 4,
            "pending_capacity": 2,
            "current_capacity": 2,
            "convergence_delta": 2
        },
        {
            "timestamp": "2013-01-01T00:05:01.000001Z",
            "_message": "Active server",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000003",
            "server_id": "11111111-0000-0000-0000-00000000001",
            "event_type": "server.active",
            "is_error": False
        },
        {
            "timestamp": "2013-01-01T00:05:02.000001Z",
            "_message": "Server is Active",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000004",
            "server_id": "11111111-0000-0000-0000-00000000002",
            "event_type": "server.active",
            "is_error": False
        }
    ]),

    ("Force deleting a group successfully", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Delete group (force).",
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "event_type": "request.group.delete.ok",
            "is_error": False,
            "desired_capacity": 0,
            "previous_desired_capacity": 2,
            "pending_capacity": 0,
            "current_capacity": 2
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": "Deleting 10 new servers to satisfy desired capacity",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000002",
            "as_user_id": "10000",
            "event_type": "convergence.scale_down",
            "is_error": False,
            "desired_capacity": 0,
            "current_capacity": 2,
            "pending_capacity": 0,
            "convergence_delta": -2
        },
        {
            "timestamp": "2013-01-01T00:05:03.000001Z",
            "_message": "Deleted server",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000003",
            "server_id": "11111111-0000-0000-0000-00000000001",
            "event_type": "server.delete",
            "is_error": False
        },
        {
            "timestamp": "2013-01-01T00:05:01.000001Z",
            "_message": "Deleted server",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000004",
            "server_id": "11111111-0000-0000-0000-00000000002",
            "event_type": "server.delete",
            "is_error": False
        }
    ]),

    ("Random bit of convergence (triggered by external deletion)", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Starting 1 new server to satisfy desired capacity",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "as_user_id": "10000",
            "event_type": "convergence.scale_up",
            "is_error": False,
            "desired_capacity": 5,
            "current_capacity": 4,
            "pending_capacity": 1,
            "convergence_delta": 1
        },
        {
            "timestamp": "2013-01-01T00:05:01.000001Z",
            "_message": "Server is Active",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000002",
            "server_id": "11111111-0000-0000-0000-00000000002",
            "event_type": "server.active",
            "is_error": False
        }
    ]),

    ("Updating group configuration partially successfully", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Attempt to update the group configuration.",
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "data": {
                "name": "new name", "cooldown": 5, "minEntities": 2,
                "maxEntities": 5, "metadata": {}
            },
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "event_type": "request.group.config.update.ok",
            "is_error": False,
            "desired_capacity": 2,
            "previous_desired_capacity": 0,
            "current_capacity": 0
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": "Starting 2 new servers to satisfy desired capacity",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000002",
            "as_user_id": "10000",
            "event_type": "convergence.scale_up",
            "is_error": False,
            "desired_capacity": 2,
            "pending_capacity": 2,
            "current_capacity": 0,
            "convergence_delta": 2
        },
        {
            "timestamp": "2013-01-01T00:00:03.000001Z",
            "_message": "Error creating server: Nova server limit has been reached",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000003",
            "event_type": "error.nova_error.absolute_limits",
            "is_error": True,
            "fault": {
                "message": "upstream API error from Nova",
                "details": {
                    "overLimit": {
                        "code": 413,
                        "message": "OverLimit Retry...",
                        "details": "Error Details...",
                        "retryAt": "2010-08-01T00:00:00Z"
                    }
                }
            }
        },
        {
            "timestamp": "2013-01-01T00:05:01.000001Z",
            "_message": "Server is Active",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000004",
            "server_id": "11111111-0000-0000-0000-00000000002",
            "event_type": "server.active",
            "is_error": False
        }
    ]),

    ("Error while scaling up because the user deleted the image", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Execute scaling policy.",
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "policy_id": "20000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "event_type": "request.policy.execute.ok",
            "is_error": False,
            "desired_capacity": 4,
            "previous_desired_capacity": 2,
            "pending_capacity": 0,
            "current_capacity": 2
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": "Starting 2 new servers to satisfy desired capacity",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000002",
            "as_user_id": "10000",
            "event_type": "convergence.scale_up",
            "is_error": False,
            "desired_capacity": 4,
            "pending_capacity": 2,
            "current_capacity": 2,
            "convergence_delta": 2
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": ("Could not find image "
                         "52415800-8b69-11e0-9b19-734f6f007777"),
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000003",
            "event_type": "error.invalid_launch_config.no_image",
            "is_error": True,
            "fault": {
                "message": "upstream API error from Nova",
                "details": {
                    "badRequest": {
                        "message": "Can not find requested image",
                        "code": 400
                    }
                }
            }
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": ("Could not find image "
                         "52415800-8b69-11e0-9b19-734f6f007777"),
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000004",
            "event_type": "error.invalid_launch_config.no_image",
            "is_error": True,
            "fault": {
                "message": "upstream API error from Nova",
                "details": {
                    "badRequest": {
                        "message": "Can not find requested image",
                        "code": 400
                    }
                }
            }
        }
    ]),

    ("Error while scaling up because the user deleted the load balancer", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Execute scaling policy.",
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "policy_id": "20000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "event_type": "request.policy.execute.ok",
            "is_error": False,
            "desired_capacity": 4,
            "previous_desired_capacity": 2,
            "current_capacity": 2
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": "Starting 2 new servers to satisfy desired capacity",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000002",
            "as_user_id": "10000",
            "event_type": "convergence.scale_up",
            "is_error": False,
            "desired_capacity": 4,
            "pending_capacity": 2,
            "current_capacity": 2,
            "convergence_delta": 2
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": ("Could not find load balancer "
                         "52415800-8b69-11e0-9b19-734f6f007777"),
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000003",
            "event_type": "error.invalid_launch_config.no_load_balancer",
            "is_error": True,
            "fault": {
                "message": "upstream API error from Load Balancers",
                "details": {
                    "message": "Load balancer not found",
                    "code": 404
                }
            }
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": ("Could not find load balancer "
                         "52415800-8b69-11e0-9b19-734f6f007777"),
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000004",
            "event_type": "error.invalid_launch_config.no_load_balancer",
            "is_error": True,
            "fault": {
                "message": "upstream API error from Load Balancers",
                "details": {
                    "message": "Load balancer not found",
                    "code": 404
                }
            }
        }
    ]),

    ("Error while scaling up because of upstream API error", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": "Execute scaling policy.",
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "policy_id": "20000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "event_type": "request.policy.execute.ok",
            "is_error": False,
            "desired_capacity": 4,
            "previous_desired_capacity": 2,
            "current_capacity": 2
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": "Starting 2 new servers to satisfy desired capacity",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000002",
            "as_user_id": "10000",
            "event_type": "convergence.scale_up",
            "is_error": False,
            "desired_capacity": 4,
            "pending_capacity": 2,
            "current_capacity": 2,
            "convergence_delta": 2
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": ("Could not find load balancer "
                         "52415800-8b69-11e0-9b19-734f6f007777"),
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000003",
            "event_type": "failure.upstream.load_balancer.response_invalid",
            "is_error": True,
            "fault": {
                "message": "upstream API error from Load Balancers",
                "details": {
                    "message": ("Out of virtual IPs. Please contact support "
                                "so they can allocate more irtual IPs."),
                    "code": 500
                }
            }
        },
        {
            "timestamp": "2013-01-01T00:00:02.000001Z",
            "_message": ("Could not find load balancer "
                         "52415800-8b69-11e0-9b19-734f6f007777"),
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "parent_id": "00000000-0000-0000-0000-00000000002",
            "transaction_id": "00000000-0000-0000-0000-00000000004",
            "event_type": "failure.upstream.load_balancer.response_invalid",
            "is_error": True,
            "fault": {
                "message": "upstream API error from Load Balancers",
                "details": {
                    "message": ("Out of virtual IPs. Please contact support "
                                "so they can allocate more irtual IPs."),
                    "code": 500
                }
            }
        }
    ]),

    ("Error while executing policy because the cooldown limit has been hit", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": ("Failed to execute policy - maximum group size "
                         "limit of 2 hit, cannot scale up by 2 servers"),
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "policy_id": "20000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "event_type": "request.policy.execute.failure.max_servers",
            "is_error": True,
            "fault": {
                "code": 403,
                "message": "Maximum group size hit",
                "details": {
                    "max_size": 2
                }
            },
            "desired_capacity": 2,
            "previous_desired_capacity": 2,
            "current_capacity": 2
        }
    ]),

    ("Error while executing policy because the cooldown limit has been hit", [
        {
            "timestamp": "2013-01-01T00:00:01.000001Z",
            "_message": ("Failed to execute policy - maximum group size "
                         "limit of 2 hit, cannot scale up by 2 servers"),
            "request_ip": "85.125.12.1",
            "user_id": "11111",
            "tenant_id": "000001",
            "scaling_group_id": "10000000-0000-0000-0000-00000000001",
            "policy_id": "20000000-0000-0000-0000-00000000001",
            "transaction_id": "00000000-0000-0000-0000-00000000001",
            "event_type": "request.policy.execute.failure.cooldown",
            "is_error": True,
            "fault": {
                "code": 403,
                "message": "Maximum group size hit",
                "details": {
                    "cooldown_remaining": 20
                }
            },
            "desired_capacity": 2,
            "previous_desired_capacity": 2,
            "current_capacity": 2
        }
    ])
]


import json
import treq
from twisted.internet.defer import gatherResults
from twisted.internet.task import react


def iter_events():
    """
    Returns those json events as a single iterator of strings, with @version
    added and timestamp converted to logstash @timestmap
    """
    for blob in (event for _, events in examples for event in events):
        blob['@timestamp'] = blob.pop('timestamp')
        blob['@version'] = 1
        yield json.dumps(blob)


def index(event):
    """
    Index an event (which should already be in json string format)
    """
    d = treq.post('http://localhost:9200/history/event', event)
    return d.addCallback(treq.content)


def get_mapping(_):
    """
    Downloads event mapping from elastic search
    """
    print('Getting mapping')
    d = treq.get('http://localhost:9200/history/_mapping')
    d.addCallback(treq.json_content)

    def write(dictionary):
        print('writing dictionary')
        with open('history.mapping.result.json', 'wb') as f:
            json.dump(dictionary, f, indent=2)

    return d.addCallback(write)


def ensure_index(event_mapping=None):
    """
    Creates the index from scratch, loading the event mapping if provided
    """
    d = treq.head('http://localhost:9200/history')

    def clean(response):
        if response.code == 200:
            print('deleting and recreating index')
            return treq.delete('http://localhost:9200/history')

    def ensure(_):
        d = treq.put('http://localhost:9200/history')
        d.addCallback(treq.json_content)
        return d.addCallback(print)

    d.addCallback(clean).addCallback(ensure)

    def put_mapping(_):
        print("Putting mapping {0}".format(event_mapping))
        with open(event_mapping) as f:
            d = treq.put('http://localhost:9200/history/event/_mapping',
                         f.read())
            return d.addCallback(treq.json_content).addCallback(print)

    if event_mapping is not None:
        d.addCallback(put_mapping)

    return d


def index_and_get_map(reactor, event_mapping=None):
    """
    Loads everything into elasticsearch and downloads the resulting mapping
    """
    d = ensure_index(event_mapping)
    d.addCallback(
        lambda _: gatherResults([index(event) for event in iter_events()]))
    d.addCallback(get_mapping)
    return d


def clean_es(reactor):
    """
    Drops everythin from elasticsearch
    """
    return treq.delete('http://localhost:9200/_all')


def print_json():
    """
    Prints all the events in pretty JSON format.
    """
    for event in iter_events():
        print(json.dumps(json.loads(event), indent=2))
        raw_input()


if __name__ == "__main__":
    # react(clean_es)
    react(index_and_get_map, ['history.mapping.json'])
