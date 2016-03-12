.. _delete-a-scaling-group:

Delete a scaling group
~~~~~~~~~~~~~~~~~~~~~~
You can use the Auto Scale API to deactivate and delete one or
more scaling groups. Your options for deleting the scaling group
depend on whether your scaling group has active entities or not.

When a group contains no servers, you can eliminate the group by
sending a DELETE request to its group ID.

The following two options are possible for deleting a scaling group:

  * If there are no active entities in your configuration, use the
    DELETE request to delete the scaling group.

  * If there are active entities, then force delete the group by submitting
    a DELETE request with `force` parameter to true.


**Delete a scaling group with no active entities**

To delete a scaling policy group that has no active entities, submit
a DELETE request with the `tenantID` and `groupIDparameters` specified in
the request URL as shown in the following example:

.. code::

     http -vv DELETE https://dfw.autoscale.api.rackspacecloud.com/v1.0/676873/groups/605e13f6-1452-4588-b5da-ac6bb468c5bf/ X-Auth-Token:XXXXXXXXXXXXXXXX

If the DELETE request is successful, a 204 response code with no response
body will be returned. If the request fails, a 403 response code will
be returned with a message stating that your group still has active
entities as shown in the following example:

.. code::

     Group d5f5f3ad-faef-4c8f-99c4-0e931189c521 for tenant 829409 still has entities.


**Delete a scaling group using FORCE DELETE**

The Auto Scale API provides an option for users to force delete a
scaling group that has active servers. The FORCE DELETE option will
remove all servers in the configuration from the load balancer(s)
and then delete the server.

.. warning::
   Using FORCE DELETE will remove all servers that are associated with the
   scaling group. Users are discouraged from using the FORCE DELETE
   option and to manually delete servers instead.

To use the FORCE DELETE option, submit a DELETE request with the
`tenantId` and `groupIdparameters` specified in the request URL,
and set the `force` parameter to `true`.

.. code::

     DELETE /{tenantId}/groups/{groupId}?force=true

Upon successful submission of this request the `minEntities` and `maxEntities`
parameters will automatically be set to 0 and the deletion of the
group will begin. If the DELETE request is successful, a 204
response code with an empty response body will be returned.
