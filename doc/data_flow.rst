=========
Data Flow
=========

Diagram
-------

.. image:: data_and_execution_workflow.png


All autoscaling information is stored in Cassandra and accessed via a model
layer which knows about the schema.  The red parts are not yet implemented.


**User-specified information**
------------------------------

This is the information that the user provides that define the hows and the
scope of the scaling group.


* the scaling group config, containing metadata, the name, and the min/max
  number of servers
* the scaling group launch config (information on how to set up a server)
* the scaling policies associated with the group
* the webhooks that allow the scaling policies to be executed.

Access
^^^^^^

The user-specified information is accessed and modified by the user via the
REST API.

It is also accessed (but not modified) by the controller, which needs the
config (to enforce limits on how many servers can be started or shut down) and
the launch config (to actually tell the launch config to start servers).


**Group State information**
---------------------------

This is the information that autoscaling generates to keep track of which
entities are part of the scaling group.

* the ids of the entities that are already up and running (active)
* the ids, or job ids, of the entities that are being spun up (pending)

Access
^^^^^^

The group state information is accessed and modified mainly by the controller,
although the REST API may read from this information to present it to the user,
and the REST API also deletes this information as part of group delete.

Every controller action should be atomic, so any controller (also the REST API
when it deletes the group) will first acquire a lock before modifying or
reading any information, and then it will release the lock.


**Job State information (tentative)**
-------------------------------------

This is a store for supervisors to coordinate/keep track of the statuses of
jobs allocated to workers.

Access
^^^^^^

Only supervisors can access or modify this information.  Whether or not to
lock TBD.


**Example Scenarios**
---------------------

User executes policy
^^^^^^^^^^^^^^^^^^^^

* The REST API looks up the policy in Cassandra, and tells the controller to
  execute said policy

* The controller acquires a lock

* The controller looks up config, policy, state, and launch information.  It
  figures out the desired change based the change specified by the policy and
  the current number of active and pending servers.  It then constraints this
  by the min/max upon the min/max.

  If the change is not zero, it tells the supervisor that this change should be
  made, passes the supervisor the launch config, and the supervisor will
  enact the changes, returning a set of job IDs for pending servers.

  The controller then stores the job IDs from the supervisor as pending servers.

* The controller releases the lock

* The supervisor starts X number of workers to implement the change, recording
  the state of the job(s) in Cassandra.

* As each job finishes, the supervisor tells the controller that the job has
  been completed.  For each of these jobs:

  * The controller acquires a lock

  * The controller removes the job from pending and places a server ID in active

  * The controller releases the lock


User modifies the config
^^^^^^^^^^^^^^^^^^^^^^^^

* The REST API updates the config, and tells the controller that the config
  has been modified

* The controller acquires a lock

* The controller looks up launch and config information, calculates the desired
  change, if any, based on the current min/max and the current number of
  servers, and potentially passes this number (and the launch) to the supervisor
  to enact the change.  See above scenario regarding what happens if desired
  servers != 0.

* The controller releases the lock


User deletes a server from Nova (not implemented)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* The Event Feed poller notices that a server has been deleted, and notifies
  the controller.

* The controller looks up/verifies which group the server belongs to.

* The controller acquires a lock

* The controller looks up config information, calculates the desired increase
  (based on how many servers have been deleted and what the current min/max
  and number of servers is) and maybe tells the supervisor to start up some
  servers to compensate for the deleted servers. See above scenario regarding
  what happens if desired servers != 0.
