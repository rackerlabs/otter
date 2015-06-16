============================
Disk Configuration Extension
============================

The disk configuration extension adds a ``OS-DCF:diskConfig`` attribute
on images and servers that controls how the disk is partitioned when
servers are created, rebuilt, or resized. A server inherits the
``OS-DCF:diskConfig`` value from the image it was created with, and an
image inherits the ``OS-DCF:diskConfig`` value of the server from which
it was created. To override the inherited setting, you can include the
``OS-DCF:diskConfig`` attribute in the request body of a server create,
rebuild, or resize request.

.. important::
   If an image has ``OS-DCF:diskConfig`` value of ``MANUAL``, you cannot
   create a server from that image with a ``OS-DCF:diskConfig`` value of
   ``AUTO``.

Valid ``OS-DCF:diskConfig`` values are:

*  ``AUTO``. The server is built with a single partition the size of the
   target flavor disk. The file system is automatically adjusted to fit
   the entire partition. This keeps things simple and automated.
   ``AUTO`` is valid only for images and servers with a single partition
   that use the EXT3 file system. This is the default setting for
   applicable Rackspace base images.
*  ``MANUAL``. The server is built using whatever partition scheme and
   file system is in the source image. If the target flavor disk is
   larger, the remaining disk space is left unpartitioned. This enables
   images to have non-EXT3 file systems, multiple partitions, and so on,
   and enables you to manage the disk configuration.

.. note::
   Although Rackspace Windows images are configured with a
   ``OS-DCF:diskConfig`` value of ``MANUAL``, the NTFS file system expands
   to the entire partition on only the first boot.

Resizing down requires the server to have a ``OS-DCF:diskConfig`` value
of ``AUTO``.

The namespace for this extended attribute is:

.. code::

    xmlns:OS-DCF="http://docs.openstack.org/compute/ext/disk_config/api/v1.1"

Changes to Get Server/Image Details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A **GET** request against the **/servers/detail**,
**/servers/**\ *``id``*, **/images/detail**, or **/images/**\ *``id``*
resource returns the ``OS-DCF:diskConfig`` extended attribute. See the
following sections.

Changes to Create Server
~~~~~~~~~~~~~~~~~~~~~~~~

When you create a server from an image with the ``OS-DCF:diskConfig``
value set to ``AUTO``, the server is built with a single partition that
is expanded to the disk size of the flavor selected. When you set the
``OS-DCF:diskConfig`` attribute to ``MANUAL``, the server is built by
using the partition scheme and file system that is in the source image. 
If the target flavor disk is larger, remaining disk space is left
unpartitioned. A server inherits the ``OS-DCF:diskConfig`` attribute
from the image from which it is created. However, you can override the
``OS-DCF:diskConfig`` value when you create a server, as follows:

**Example: Create Server with OS-DCF:diskConfig: JSON Request**

.. code::

    {
        "server" : {
            "name" : "new-server-test",
            "imageRef" : "5f68715f-201f-4600-b5a1-0b97e2b1cb31",
            "flavorRef" : "2",
            "OS-DCF:diskConfig" : "MANUAL",
            "metadata" : {
                "My Server Name" : "Ubuntu 10.04 LTS manual" 
            },
            "personality" : [
                {
                    "path" : "/etc/banner.txt",
                    "contents" : "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp dCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5k IGF0IHN1Y2ggYSBzcGVlZC4uLkl0IGZlZWxzIGFuIGltcHVs c2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vdy4g QnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRo ZSBwYXR0ZXJucyBiZWhpbmQgYWxsIGNsb3VkcywgYW5kIHlv dSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vy c2VsZiBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6 b25zLiINCg0KLVJpY2hhcmQgQmFjaA==" 
                } 
            ] 
        }
    }

In this example, the server is created with ``OS-DCF:diskConfig`` set to
``MANUAL``, regardless of what value the image ``OS-DCF:diskConfig``
attribute is set to. Images also inherit the ``OS-DCF:diskConfig`` value
from a server. So, if an image is created from the server, it also has a
``OS-DCF:diskConfig`` value of ``MANUAL``.

Changes to Rebuild Server
~~~~~~~~~~~~~~~~~~~~~~~~~

You can set the ``OS-DCF:diskConfig`` attribute when you rebuild a
server. In the following examples, the ``OS-DCF:diskConfig`` attribute
is set to ``MANUAL``, which allows unused disk space to be used for
other partitions after the server is rebuilt.

If you do not set the ``OS-DCF:diskConfig`` attribute is not set during
the rebuild, the original value of the attribute is retained.

**Example: Rebuild Server with OS-DCF:diskConfig: JSON Request**

.. code::

                        {
    "rebuild" : {
             "name" : "new-server-test",
             "imageRef" : "d42f821e-c2d1-4796-9f07-af5ed7912d0e",
             "flavorRef" : "2",
             "OS-DCF:diskConfig" : "manual",
             "adminPass" : "diane123",
             "metadata" : {
                  "My Server Name" : "Apache1"
                   },
             "personality" : [
                 {
                   "path" : "/etc/banner.txt",
                   "contents" : "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBrbm93IHdoeSBp dCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5k IGF0IHN1Y2ggYSBzcGVlZC4uLkl0IGZlZWxzIGFuIGltcHVs c2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vdy4g QnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRo ZSBwYXR0ZXJucyBiZWhpbmQgYWxsIGNsb3VkcywgYW5kIHlv dSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vy c2VsZiBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6 b25zLiINCg0KLVJpY2hhcmQgQmFjaA=="
                 }
               ]
        }
    }

Changes to Resize Server
~~~~~~~~~~~~~~~~~~~~~~~~

You can set the ``OS-DCF:diskConfig`` attribute when you resize a
server, which enables you to change the value of the attribute when you
scale a server up or down.

If you do not set the ``OS-DCF:diskConfig`` attribute during the resize,
the original value of the attribute is retained.

**Example: Resize Server with OS-DCF:diskConfig: JSON Request**

.. code::

                        {
        "resize" : {
            "flavorRef" : "3",
            "OS-DCF:diskConfig" : "manual"
        }
    }
