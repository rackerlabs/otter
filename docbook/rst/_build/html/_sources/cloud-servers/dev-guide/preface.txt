=======
Preface
=======

Next generation Cloud Servers `powered by
OpenStack <http://www.rackspace.com/cloud/openstack/>`__ is a fast,
reliable, and scalable cloud compute solution without the risk of
proprietary lock-in. It provides the core features of the OpenStack
Compute *API* v2 and also deploys certain extensions as permitted by the
OpenStack Compute API contract. Some of these extensions are generally
available through OpenStack while others implement Rackspace-specific
features to meet customers’ expectations and for operational
compatibility. The OpenStack Compute API and the Rackspace extensions
are known collectively as API v2.

.. important:: During 2015, all First Generation servers will be migrated to
   Next Generation servers, on a rolling basis.

   Notification from Rackspace will be sent to customers informing them of
   their 30-day window to complete the migration of the specified servers.
   If you take no action, your server will be migrated for you.

   To migrate your servers, during your migration window, simply perform a
   ``SOFT`` reboot on your first gen server, either from the Control Panel
   or by using the reboot API operation. The migration process will
   preserve all data and configuration settings.

   During the 30-day migration window, performing a ``HARD`` reboot on a
   first gen server will reboot the server without triggering the
   migration.

   You can see information about your migration window's open and close
   dates, use the Get Server Details on your first gen server, and look in
   the metadata section of the response for
   "FG2NG\_self\_migration\_available\_till" and
   "FG2NG\_self\_migration\_available\_from" key pairs. If your migration
   window has not been scheduled, you will not see these metadata keys.

   For more information about the server migration see the Knowledge Center
   article: `*First Generation to Next Generation cloud server migration
   FAQ* <http://www.rackspace.com/knowledge_center/article/first-generation-to-next-generation-cloud-server-migration-faq>`__

This document describes the features available with API v2.

We welcome feedback, comments, and bug reports. Log into the Rackspace
customer portal at https://feedback.rackspace.com/.

Intended Audience
-----------------

This guide assists software developers who want to develop applications
by using next generation Cloud Servers. To use this information, you should
have access to an active Rackspace Cloud Servers account and you should also be familiar with the following concepts:

-  Rackspace Cloud Servers service

-  *RESTful* web services

-  *HTTP*/1.1

-  JSON data serialization format

