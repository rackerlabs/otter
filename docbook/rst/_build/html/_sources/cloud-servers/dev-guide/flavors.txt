=======
Flavors
=======

The term flavor refers to a server's combination of RAM size, vCPUs, network
throughput (RXTX factor), and disk space. You build a Linux or Windows server
by choosing its flavor. You also use flavors to choose between cloud servers,
which are multi-tenant virtual servers, and OnMetal servers, which are
single-tenant physical servers.

Virtual Cloud Server Flavors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Virtual Cloud Server Flavors are divided into the following classes:

**Standard**
    These flavors, which are being phased out and should not be used for
    new servers, have the following characteristics:

    -  Sizes range from 512 MB to 30 GB.

    -  These flavors are recommended for general-purpose workloads.

    -  They use a single disk for system and data information storage.

    -  All storage is located on RAID 10-protected SATA hard disk
       drives.

**General Purpose v1**
    These flavors, formerly Performance 1, have the following
    characteristics:

    -  Sizes range from 1 GB to 8 GB.

    -  Linux servers can be any size. Windows servers must be 2 GB or
       larger.

    -  These flavors are useful for many use cases, from general-purpose
       workloads to high performance websites.

    -  They use a single disk for system and data information storage.

    -  vCPUs are oversubscribed and “burstable”, which means that there
       are more vCPUs allocated to the Cloud Servers on a physical host
       than there are physical CPU threads. This over-subscription model
       assumes that under normal conditions not all vCPUs will be needed
       by all Cloud Servers at the same time, and allows your Cloud
       Server to take advantage of those additional resources during
       such times of under-utilization.

    -  All storage is located on RAID 10-protected SSD hard disk drives.

**I/O v1**
    These flavors, formerly Performance 2, have the following
    characteristics:

    -  Sizes range from 15 GB to 120 GB.

    -  These flavors are ideal for high performance applications and
       databases that benefit from fast disk I/O, such as Cassandra and
       MongoDB.

    -  They have separate system and data disks.

    -  vCPUs are “reserved”, which means that there are never more vCPUs
       allocated to the Cloud Servers on a physical host than there are
       physical CPU threads on that host. This model ensures that your
       Cloud Server will always have full access to all its vCPUs.

    -  All storage is located on RAID 10-protected SSD hard disk drives.

**Compute v1**
    These flavors have the following characteristics:

    -  Sizes range from 3.75 GB to 60 GB.

    -  These flavors are optimized for web servers, application servers,
       and other CPU-intensive workloads.

    -  They have no local data disks.

    -  They are backed by Cloud Block Storage (additional charges apply
       for Cloud Block Storage).

    -  vCPUs are “reserved”, which means that there are never more vCPUs
       allocated to the Cloud Servers on a physical host than there are
       physical CPU threads on that host. This model ensures that your
       Cloud Server will always have full access to all its vCPUs.

    -  All storage is located on RAID 10-protected SSD hard disk drives.

**Memory v1**
    These flavors have the following characteristics:

    -  Sizes range from 15 GB to 240 GB.

    -  These flavors are recommended for memory-intensive workloads.

    -  They have no local data disks.

    -  They are backed by Cloud Block Storage (additional charges apply
       for Cloud Block Storage).

    -  vCPUs are “reserved”, which means that there are never more vCPUs
       allocated to the Cloud Servers on a physical host than there are
       physical CPU threads on that host. This model ensures that your
       Cloud Server will always have full access to all its vCPUs.

    -  All storage is located on RAID 10-protected SSD hard disk drives.

If you require additional storage beyond what is provided by the local
disks on a specific flavor, you can extend all the preceding server
flavors with Cloud Block Storage.

OnMetal Cloud Server Flavors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

OnMetal Cloud Server flavors differ significantly from Virtual Cloud
Server flavors. Virtual Cloud Server flavors are used to create virtual
servers with a hypervisor to manage multi-tenancy, which means one or
more virtual instances are located on the same physical server. OnMetal
Cloud Server flavors are used to rapidly build a server instance on a
physical server with no hypervisor and no multi-tenancy.

There are three configurations within the OnMetal flavor class.

-  **OnMetal Compute** - recommended for high CPU activity like network
   requests, application logic, web servers, load balancers, and so on.

-  **OnMetal Memory** - recommended for high RAM activity like in-memory
   SQL configurations, caching, searching indexes, and so on.

-  **OnMetal I/O** - recommended for high I/O activity like NoSQL and
   SQL databases.

OnMetal server disk space may not be extended with Cloud Block Storage.

Supported Flavors for Cloud Servers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Rackspace Cloud Servers service currently supports the following
flavors for next generation Cloud Servers:

**Table: Supported Flavors for Next Generation Cloud Servers**

+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| ID               | Flavor name              | Memory (MB) | Disk space | Ephemeral | VCPUs | RXTX factor |
+==================+==========================+=============+============+===========+=======+=============+
| 2                | 512 MB Standard Instance | 512         | 20         | 0         | 1     | 80.0        |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| 3                | 1 GB Standard Instance   | 1024        | 40         | 0         | 1     | 120.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| 4                | 2 GB Standard Instance   | 2048        | 80         | 0         | 2     | 240.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| 5                | 4 GB Standard Instance   | 4096        | 160        | 0         | 2     | 400.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| 6                | 8 GB Standard Instance   | 8192        | 320        | 0         | 4     | 600.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| 7                | 15 GB Standard Instance  | 15360       | 620        | 0         | 6     | 800.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| 8                | 30 GB Standard Instance  | 30720       | 1200       | 0         | 8     | 1200.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| general1-1       | 1 GB General Purpose v1  | 1024        | 20         | 0         | 1     | 200.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| general1-2       | 2 GB General Purpose v1  | 2048        | 40         | 0         | 2     | 400.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| general1-4       | 4 GB General Purpose v1  | 4096        | 80         | 0         | 4     | 800.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| general1-8       | 8 GB General Purpose v1  | 8192        | 160        | 0         | 8     | 1600.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| compute1-4       | 3.75 GB Compute v1       | 3840        | 0          | 0         | 2     | 625.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| compute1-8       | 7.5 GB Compute v1        | 7680        | 0          | 0         | 4     | 1250.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| compute1-15      | 15 GB Compute v1         | 15360       | 0          | 0         | 8     | 2500.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| compute1-30      | 30 GB Compute v1         | 30720       | 0          | 0         | 16    | 5000.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| compute1-60      | 60 GB Compute v1         | 61440       | 0          | 0         | 32    | 10000.0     |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| io1-15           | 15 GB I/O v1             | 15360       | 40         | 150       | 4     | 1250.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| io1-30           | 30 GB I/O v1             | 30720       | 40         | 300       | 8     | 2500.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| io1-60           | 60 GB I/O v1             | 61440       | 40         | 600       | 16    | 5000.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| io1-90           | 90 GB I/O v1             | 92160       | 40         | 900       | 24    | 7500.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| io1-120          | 120 GB I/O v1            | 122880      | 40         | 1200      | 32    | 10000.0     |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| memory1-15       | 15 GB Memory v1          | 15360       | 0          | 0         | 2     | 625.0       |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| memory1-30       | 30 GB Memory v1          | 30720       | 0          | 0         | 4     | 1250.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| memory1-60       | 60 GB Memory v1          | 61440       | 0          | 0         | 8     | 2500.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| memory1-120      | 120 GB Memory v1         | 122880      | 0          | 0         | 16    | 5000.0      |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| memory1-240      | 240 GB Memory v1         | 245760      | 0          | 0         | 32    | 10000.0     |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| onmetal-compute1 | OnMetal Compute v1       | 32768       | 32         | 0         | 20    | 10000.0     |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| onmetal-io1      | OnMetal I/O v1           | 131072      | 32         | 3200      | 40    | 10000.0     |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
| onmetal-memory1  | OnMetal Memory v1        | 524288      | 32         | 0         | 24    | 10000.0     |
+------------------+--------------------------+-------------+------------+-----------+-------+-------------+
