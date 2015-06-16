
.. _autoscale-dg-overview:

Overview
~~~~~~~~~

Rackspace Auto Scale is a web service that automatically scales
resources in response to an increase or decrease in overall workload
based on user-defined policies. You can set up a schedule for launching
Auto Scale or define an event that is triggered by Cloud Monitoring. You
can also specify a minimum and maximum number of cloud servers, the
amount of resources that you want to increase or decrease, and the
thresholds in Cloud Monitoring that trigger the scaling activities.

To use Auto Scale, you define a scaling group consisting of cloud
servers and cloud load balancers or RackConnect v3. Then you define
policies, either schedule-based or monitoring-based. For
monitoring-based policies, you define cloud monitoring alerts to watch
the group's activity, and you define scaling rules to change the scaling
group's configuration in response to alerts. For schedule-based
policies, you simply set a schedule. Because you can change a scaling
group's configuration in response to changing workloads, you can begin
with a minimal cloud configuration and grow only when the cost of that
growth is justified.

**Related information**

-  :ref:`Additional resources <autoscale-dg-additional-resources>`

-  :ref:`Pricing and service level <autoscale-dg-pricing-and-service-level>`
