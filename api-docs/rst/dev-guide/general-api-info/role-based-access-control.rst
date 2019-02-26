.. _rbac:

Role-based access control (RBAC)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Role-based access control (RBAC) restricts access to the capabilities of
Rackspace Cloud services, including the Cloud Rackspace Auto Scale API,
to authorized users only. RBAC enables Rackspace Cloud customers to
specify which account users of their Cloud account have access to which
Rackspace Auto Scale API service capabilities, based on roles defined by
Rackspace. (See the `Auto Scale Product Roles and
Capabilities <product-roles-and-capabilities>` table). The
permissions to perform certain operations in the Rackspace Auto Scale
API – create, read, update, delete – are assigned to specific roles. The
account owner assigns these roles, either multiproduct (global) or
product-specific (for example, Auto Scale only) to account users.


.. _autoscale-assign-roles-to-users:

Assigning roles to account users
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The account owner (``identity:user-admin``) can create account users on
the account and then assign roles to those users. The roles grant the
account users specific permissions for accessing the capabilities of the
Auto Scale service. Each account has only one account owner, and that
role is assigned by default to any Rackspace Cloud account when the
account is created.

See the *Identity Client Developer Guide* for information about
how to perform the following tasks:

-  `Create account users <http://docs.rackspace.com/auth/api/v2.0/auth-client-devguide/content/POST_addUser_v2.0_users_User_Calls.html>`__

-  `Assign roles to account users <http://docs.rackspace.com/auth/api/v2.0/auth-client-devguide/content/PUT_addUserRole__v2.0_users__userId__roles_OS-KSADM__roleid__Role_Calls.html>`__

-  `Delete global role from user <http://docs.rackspace.com/auth/api/v2.0/auth-client-devguide/content/DELETE_deleteUserRole__v2.0_users__userId__roles_OS-KSADM__roleid__Role_Calls.html>`__

..  note::
      The account owner (``identity:user-admin``) role cannot hold any additional roles because it
      already has full access to all capabilities.

.. _roles-available:

Roles available for Auto Scale
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Two roles (observer and admin) can be used to access the Auto Scale API
specifically. The following table describes these roles and their
permissions.

.. _product-roles-and-capabilities:

**Table: Auto Scale Product Roles and Capabilities**

+--------------------------------------+-------------------------------------+
| Role Name                            | Role Permissions                    |
+======================================+=====================================+
| ``autoscale:admin``                  | This role provides Create, Read,    |
|                                      | Update, and Delete permissions in   |
|                                      | Auto Scale, where access is granted |
+--------------------------------------+-------------------------------------+
| ``autoscale:observer``               | This role provides Read permission  |
|                                      | in Auto Scale, where access is      |
|                                      | granted                             |
+--------------------------------------+-------------------------------------+


Additionally, two multiproduct roles apply to all products. Users with
multiproduct roles inherit access to future products when those products
become RBAC-enabled. The following table describes these roles and their
permissions.

**Table: Multiproduct (Global) Roles and Capabilities**

+--------------------------------------+-------------------------------------+
| Role Name                            | Role Permissions                    |
+======================================+=====================================+
| ``admin``                            | Create, Read, Update, and Delete    |
|                                      | permissions across multiple         |
|                                      | products, where access is granted   |
+--------------------------------------+-------------------------------------+
| ``observer``                         | Read permission across multiple     |
|                                      | products, where access is granted   |
+--------------------------------------+-------------------------------------+

.. _resolve-role-conflicts:

Resolving conflicts between RBAC multiproduct vs. custom (product-specific) roles
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The account owner can set roles for both multiproduct and Auto Scale
scope, and it is important to understand how any potential conflicts
among these roles are resolved. When two roles appear to conflict, the
role that provides the more extensive permissions takes precedence.
Therefore, admin roles take precedence over observer roles, because
admin roles provide more permissions.

The following table shows two examples of how potential conflicts
between user roles in the Control Panel are resolved.

**Table: Resolving cross-product role conflicts**

+---------------------------------+--------------------------+----------------------------+
| Permission Configuration        | View of Permission in    | Can the User Perform       |
|                                 | the Control Panel        | Product Admin Functions in |
|                                 |                          | the Control Panel?         |
+=================================+==========================+============================+
| User is assigned the following  | Appears that the user has| Yes, for Auto Scale only.  |
| roles: multiproduct **observer**| has only the mulitproduct| user has the **observer**  |
| and Auto Scale **admin**        | **observer** role.       | role for other products.   |
+---------------------------------+--------------------------+----------------------------+
| User is assigned the following  |Appears that the user has | Yes, for all the products. |
| roles: multiproduct **admin**   |only the multiproduct     | The Auto Scale **observer**|
| and Auto Scale **observer**     |**admin** role.           | role is ignored.           |
+---------------------------------+--------------------------+----------------------------+

.. _rbac-permissions:

RBAC permissions cross-reference to Auto Scale operations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

API operations for Auto Scale might not be available to all roles.
To see which operations are permitted to invoke which calls, review the
`Permissions Matrix for Auto Scale`_ article.

.. _Permissions Matrix for Auto Scale: http://www.rackspace.com/knowledge_center/article/permissions-matrix-for-auto-scale
