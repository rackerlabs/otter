=========================
Extended Status Extension
=========================

The extended status extension displays the VM, task, and power statuses
for servers.

The extension displays these statuses in the following fields in the
response bodies for the `list
servers` and `get server` calls (http://api.rackspace.com/#compute_servers).

**Extended Statuses**

``OS-EXT-STS:vm_state``: The virtual machine (VM) status. More details below.

``OS-EXT-STS:task_state``: The task status. More details below.

``OS-EXT-STS:power_state``: The power status. More details below.

.. note:: The API does not regulate the VM and task status values so it is
   possible that these status values can be added, removed, or renamed.

Currently, the possible values for the VM, task, and power status fields
are:

 **``OS-EXT-STS:vm_state``**
    The virtual machine (VM) status. Possible values are:

    -  active

    -  build

    -  deleted

    -  error

    -  paused

    -  rescued

    -  resized

    -  soft\_deleted

    -  stopped

    -  suspended

 **``OS-EXT-STS:task_state``**
    The task status. Possible values are:

    -  block\_device\_mapping

    -  deleting

    -  image\_snapshot

    -  image\_pending\_upload

    -  image\_uploading

    -  migrating

    -  networking

    -  pausing

    -  powering\_off

    -  powering\_on

    -  rebooting

    -  rebooting\_hard

    -  rebuilding

    -  rebuild\_block\_device\_mapping

    -  rebuild\_spawning

    -  rescuing

    -  resize\_confirming

    -  resize\_finish

    -  resize\_migrated

    -  resize\_migrating

    -  resize\_prep

    -  resize\_reverting

    -  resuming

    -  scheduling

    -  spawning

    -  starting

    -  stopping

    -  suspending

    -  unpausing

    -  unrescuing

    -  updating\_password

 **``OS-EXT-STS:power_state``**
    The power status. Possible values are:

    -  ``0``. The instance is powered down.

    -  ``1``. The instance is powered up.

    -  ``4``. The instance is shut off.

The following list shows the server statuses that correspond with the
VM and tasks statuses:

**Server Statuses and Corresponding VM and Task Statuses**

+---------------+---------------------+------------------------------+
| Server status | OS-EXT-STS:vm_state | OS-EXT-STS:task_state        |
+---------------+---------------------+------------------------------+
| ACTIVE        | active              | :ref:`task-states`           |
+---------------+---------------------+------------------------------+
| HARD_REBOOT   | active              | rebooting_hard               |
+---------------+---------------------+------------------------------+
| MIGRATING     | active              | migrating                    |
+---------------+---------------------+------------------------------+
| PASSWORD      | active              | updating_password            |
+---------------+---------------------+------------------------------+
| REBOOT        | active              | rebooting                    |
+---------------+---------------------+------------------------------+
| REBUILD       | active              | rebuilding                   |
+---------------+---------------------+------------------------------+
| REBUILD       | active              | rebuild_block_device_mapping |
+---------------+---------------------+------------------------------+
| REBUILD       | active              | rebuild_spawning             |
+---------------+---------------------+------------------------------+
| RESIZE        | active              | resize_prep                  |
+---------------+---------------------+------------------------------+
| RESIZE        | active              | resize_migrating             |
+---------------+---------------------+------------------------------+
| RESIZE        | active              | resize_migrated              |
+---------------+---------------------+------------------------------+
| RESIZE        | active              | resize_finish                |
+---------------+---------------------+------------------------------+
| BUILD         | building            | :ref:`task-states`           |
+---------------+---------------------+------------------------------+
| DELETED       | deleted             | :ref:`task-states`           |
+---------------+---------------------+------------------------------+
| ERROR         | error               | :ref:`task-states`           |
+---------------+---------------------+------------------------------+
| PAUSED        | paused              | :ref:`task-states`           |
+---------------+---------------------+------------------------------+
| RESCUE        | rescued             | :ref:`task-states`           |
+---------------+---------------------+------------------------------+
| VERIFY_RESIZE | resized             | :ref:`task-states`           |
+---------------+---------------------+------------------------------+
| REVERT_RESIZE | resized             | resize_reverting             |
+---------------+---------------------+------------------------------+
| DELETED       | soft_deleted        | :ref:`task-states`           |
+---------------+---------------------+------------------------------+
| SHUTOFF       | stopped             | :ref:`task-states`           |
+---------------+---------------------+------------------------------+
| SUSPENDED     | suspended           | :ref:`task-states`           |
+---------------+---------------------+------------------------------+

.. _task-states:

Task states
~~~~~~~~~~~

Possible task statuses include the following:

block_device_mapping

deleting

image_snapshot. Indicates that a create image action has been initiated and that the hypervisor is creating the snapshot. Any operations that would modify data on the server's virtual hard disk should be avoided during this time.

image_pending_upload. Indicates that the hypervisor has completed taking a snapshot of the server. At this point, the hypervisor is packaging the snapshot and preparing it for upload to the image store.

image_uploading. Indicates that the hypervisor is currently uploading a packaged snapshot of the server to the image store.

migrating

networking

pausing

powering_off

powering_on

rebooting

rebooting_hard

rebuilding

rebuild_block_device_mapping

rebuild_spawning

rescuing

resize_confirming

resize_finish

resize_migrated

resize_migrating

resize_prep

resize_reverting

resuming

scheduling

spawning

starting

stopping

suspending

unpausing

unrescuing

updating_password

The namespace for this extended attribute is:

.. code::

   xmlns:OS-EXT-STS="http://docs.openstack.org/compute/ext/extended_status/api/v1.1"

