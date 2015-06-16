==========================
Scheduled Images Extension
==========================

You may schedule daily or weekly images of your server automatically, but you
cannot schedule both daily and weekly images for a server. When you schedule an
image, a new resource is created at /servers/{serverId}/rax-si-image-schedule.
This resource, which contains the retention value and an optional day of the
week specification, indicates that this server will be monitored by the
scheduled images service.

If you do not include a day of the week specification in your scheduled images
request, the server's image will be created daily.

If you include a day of the week specification in your scheduled images
request, the server's image will be created weekly on the day you indicate.
Specify the optional day of the week using a string value from the following
enumeration: SUNDAY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY.

The scheduled images request for both daily and weekly images requires a
retention value, a positive integer, which indicates the number of images
created by the scheduled images service that will be retained in your cloud
storage account. The scheduled images service will remove scheduled images in
excess of that value, keeping the most recently created scheduled images (and
all manually created images) of that server. You may configure each server's
retention value independently.

Keep in mind:

* Smaller snapshots tend to finish more quickly.

* A very large snapshot may take so long to finish that it may block the next
   day's scheduled snapshot from occurring.

* If you have a large amount of data to save, you may wish to explore other
   backup options.

.. important::
   The scheduled images service is a "best effort service". Images are
   scheduled so that they will not interfere with each other or with on-demand
   snapshots. You may not specify a particular time at which your server
   snapshot will be taken, nor can we guarantee what time your scheduled image
   will become active, as the time that an image becomes active depends upon
   the current network traffic load, and other factors. We do guarantee that
   all users will receive the same best-effort service.

   For weekly images, you specify the day of the week (determined by UTC) when
   you'd like your server image created. As with daily scheduled images, we
   create a schedule for you and promise to satisfy it on a best-effort basis.
   There's no guarantee that your server's schedule will stay the same from
   week to week: we reserve the right to modify the time your image is made so
   that we can balance the the number of image creations in flight throughout
   the cloud and throughout the day. Additionally, as some days of the week are
   much more popular than others for scheduling images, in rare circumstances
   we may create your weekly scheduled image in a window beginning 12:00 UTC
   the day before the day of the week you specify and ending at 12:00 UTC the
   day after the day of the week you specify. This is the time your image is
   scheduled to be created. The time it will be available for you to use (that
   is, when its status is ACTIVE) depends on factors such as the size of the
   image and overall network congestion in the cloud.

The namespace for this extended element is::

   xmlns:RAX-SI="http://docs.openstack.org/servers/api/ext/scheduled_images/v1.0"