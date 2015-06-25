Glossary 
----------

**Agent**
    A monitoring daemon that resides on the server being monitored. The
    agent gathers metrics based on agent checks and pushes them to Cloud
    Monitoring.

**Agent Token**
    An authentication token used to identify the agent when it
    communicates with Cloud Monitoring.

**Alarm**
    A mechanism that contains a set of rules that determine when a
    notification is triggered.

**Authentication**
    The act or process of confirming the identity of a user or the truth
    of a claim. The authentication service confirms that an incoming
    request is being made by the user who claims to be making the
    request. The service does this by validating a set of claims that
    the user makes. These claims are initially in the form of a set of
    credentials. After initial confirmation based on credentials, the
    authentication service issues a token to the user. When making
    subsequent requests, the user can provide the token as evidence that
    the user's identity has already been authenticated.

**Check**
    A definition that explicitly specifies how you want to monitor an
    entity.

**Collector**
    Software that collects data from the monitoring zone. The collector
    is mapped directly to an individual computer or a virtual machine.

**Convergence**
    The act of Auto Scale adding or removing enough servers to satisfy
    the needed capacity.

**Convergence Delta**
    The change in the number of servers that the system makes when a
    scaling policy is executed. For example, if the convergence delta is
    2, then the system adds 2 servers. If it is -10, the system removes
    10 servers.

**Cooldown**
    There are two types of cooldown: group and policy. A group cooldown
    is the configured length of time that a scaling group must wait
    after scaling before beginning to scale again. A policy cooldown is
    the configured length of time that a scaling policy must wait before
    being able to be executed again.

**Flavor**
    A resource configuration for a server. Each flavor is a unique
    combination of disk, memory, vCPUs, and network bandwidth.

**Health Monitor**
    A configurable feature of each load balancer. A health monitor is
    used to determine whether a back-end node is usable for processing a
    request. The load balancing service currently supports active health
    monitoring.

**Image**
    A collection of files for a specific operating system (OS) that you
    use to create or rebuild a server. Rackspace provides pre-built
    images. You can also create custom images from servers that you have
    launched. Custom images can be used for data backups or as "gold"
    images for additional servers.

**Launch Configuration**
    A configuration that contains the necessary details for adding and
    removing servers from a scaling group in the Rackspace Auto Scale
    API. The ``launchConfiguration`` object specifies whether you are
    creating a server or a load balancer and the necessary details about
    the configuration.

**Load Balancer**
    A logical device that belongs to a cloud account. A load balancer is
    used to distribute workloads between multiple back-end systems or
    services, based on the criteria that is defined as part of its
    configuration.

**Node**
    A back-end device that provides a service on a specified IP and
    port.

**Notification**
    An informational message that is sent to one or more addresses when
    an alarm is triggered.

**Scaling**
    Scaling is the process of adjusting a server configuration in
    response to variations in workload.

**Scaling Group**
    A scaling group identifies servers and load balancers that are
    managed by a scaling policy.

**Scaling Policy**
    A scaling policy manages a scaling group.

**Session persistence**
    A feature of the load balancing service that attempts to force
    subsequent connections to a service to be redirected to the same
    node as long as the node is online.

**Server**
    A computer that provides explicit services to the client software
    running on its system. A server is a virtual machine (VM) instance
    in the Cloud Servers environment. To create a server, you must
    specify a name, flavor reference, and image reference.
**Virtual IP**
    An Internet Protocol (IP) address that is configured on the load
    balancer. Clients use the virtual IP to connect to a service that is
    load balanced. Incoming connections are distributed to back-end
    nodes based on the configuration of the load balancer.

**Webhook**
    A webhook is a URL that can activate a policy without
    authentication.
