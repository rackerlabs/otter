======================
Config Drive Extension
======================

Config_drive is a read-only configuration drive that is attached to server
instances on boot. It is given the label "config-2", and it shows up as a CDROM
drive on the instance. It is especially useful in conjunction with cloud-init
(a server bootstrapping application) and for passing large files to be used by
your server.

To use the config drive, once it is attached to a server, you need to mount it.
Mounting instructions vary by operating system. For some Linux operating
systems, for example, you might issue the following two instructions:

           # mkdir -p /mnt/config
           # mount /dev/disk/by-label/config-2 /mnt/config

When a config drive is created, it is configured by data contained in one or
both of the following arguments:

**user_data**
   Contained in openstack/latest/user_data

.. note::
   If the content of the user_data file is not purely text, convert it by using
   base64 encoding to allow for proper transfer and storage. If your user_data
   needs to be encoded and isn't, you'll get an 400 Userdata content cannot be
   decoded message.

   Encoded user-data is a base64 encoded string and adheres to one of a few
   specs (depending on the Linux distribution): Ubuntu-style and CoreOS-style.

**personality**
   Located in openstack/content/0000 with the path listed in the
   openstack/latest/meta_data.json file.

The following list shows files present in the config drive if both user-data and personality arguments are passed during server creation:

* ec2/2009-04-04/meta-data.json

* ec2/2009-04-04/user-data

* ec2/latest/meta-data.json

* ec2/latest/user-data

* openstack/2012-08-10/meta_data.json

* openstack/2012-08-10/user_data

* openstack/content

* openstack/content/0000

* openstack/content/0001

* openstack/latest/meta_data.json

* openstack/latest/user_data
