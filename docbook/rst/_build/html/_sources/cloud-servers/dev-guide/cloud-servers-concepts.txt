Cloud Servers Concepts
----------------------

To use the next generation Cloud Servers service with or without the
Cloud Networks extension you should understand these key concepts:


Server
   A virtual machine (VM) instance running on a host. To create a server, you
   must specify a name, flavor reference, and image reference.

Host
   A physical server running multiple VM instances.

Flavor
   A resource configuration for a server. Each flavor is a unique combination
   of disk space, memory capacity, vCPUs, and network bandwidth. See flavors.

Image
   A collection of files for a specific operating system (OS) that you use to
   create or rebuild a server. Rackspace provides pre-built images. You can
   also create custom images from servers that you have launched. Custom images
   can be used for data backups or as "gold" images for additional servers.

Reboot
   This action performs either a soft or hard reboot of a server. A soft reboot
   is a graceful shutdown and restart of the operating system on your server. A
   hard reboot power cycles your server, which performs an immediate shutdown
   and restart.

Rebuild
   This action removes all data on the server and replaces it with the
   specified image. Server ID and IP addresses on the server remain the same.

Resize
   This action converts an existing server to a different flavor, which scales
   the server up or down. The original server is saved for a period of time to
   allow rollback if a problem occurs. You can confirm or revert a resize. A
   confirmed resize removes the original server. A reverted resize restores the
   original server. All resizes are automatically confirmed after 24 hours if
   you do not explicitly confirm or revert them.

CIDR
   Classless Inter-Domain Routing (CIDR). A method for allocating IP addresses
   and routing Internet Protocol packets. When you create an isolated network
   through Cloud Networks, you specify a CIDR.

isolated network
   A virtual Layer 2 network that your create through Cloud Networks and that
   you can attach to a new Next Generation Cloud Server. Use an isolated
   network to keep your server separate from the Rackspace network, the
   Internet, or both. When you create a isolated network, it is associated with
   your tenant ID.

PublicNet
   Provides access to the Internet, Rackspace services such as Cloud
   Monitoring, Managed Operations Service Level, RackConnect, Cloud Backup, and
   certain operating system updates. When you list networks through Cloud
   Networks, PublicNet is labeled public.

ServiceNet
   An internal only, multi-tenant network connection within each Rackspace data
   center. Provides access to Rackspace services, such as Cloud Files, Cloud
   Databases, Cloud Backup, and to certain packages and patches. ServiceNet IPs
   are not accessible from the Internet and are local to each data center. You
   can configure your account resources to use a ServiceNet IP address so that
   traffic over the internal network is not billed. When you list networks
   through Cloud Networks, ServiceNet is labeled as private.

