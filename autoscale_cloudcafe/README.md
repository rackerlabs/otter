AUTOSCALE CLOUDCAFE
======================================
<pre>
	                 _ ___
	  .----.        ( `   )
     / c  ^ `,     (   )   ) _
     |     .--'   (__.____`)__)
      \   (          ) )
      /  -.\          ( (
     / .   \       .........
    /  \    ',-~.._|       |
   ;    `- ,_ ,,.[_|   T   |
   |      /        |       |
   |      |         '-...-'
   |    __|
   ;   /   \
  ,'        |
 (_`'---._ /--,
   `'---._`'---..__
          `''''--, )
            _.-'`,`
            ````
</pre>
======================================

The Autoscale Cloud Common Automation Framework Engine is designed to be used as the base engine for building an automated framework for autoscale API and non-UI resource testing. It is designed to support smoke, functional, integration and system testing. It requires both Open Cafe and Cloud Cafe to be installed.

 Open Cafe - https://github.com/stackforge/opencafe

 It is the core engine that provides a model, a pattern and assorted common tools for building automated tests. It provides its own light weight unittest based runner, however, it is designed to be modular. It can be extended to support most test case front ends/runners (nose, pytest, lettuce, testr, etc...) through driver plug-ins.

 Cloud Cafe - https://github.com/stackforge/cloudcafe

 It is an implementaion of the Open Cafe and has drivers for the rackspace open sourced products such as Nova, Block storage etc.

 Getting started guide: https://one.rackspace.com/display/~daryl.walleck/Getting+Started+With+CloudCafe#GettingStartedWithCloudCafe

Configuration
--------------
Autoscale Cloudcafe's configurations will be installed to: USER_HOME/.cloudcafe/configs/autoscale/

Once the Open CAFE Core engine, the CloudCAFE Framework implementation are installed and Autoscale CloudCAFE is cloned, you are now
ready to:

1) Execute the test cases for autoscale api.

                       or

2) Write entirely new tests in this repository using the CloudCAFE Framework.

Running Tests
--------------
Tests can be run regardless of the current directory. The format of the runner is as follows:

cafe-runner autoscale CONFIG(minus .config) PARAMS

Example:
cafe-runner autoscale dev -p functional --parallel
    runs all the autoscale tests under the functional folder in parallel
cafe runner autoscale dev -m test_create_scaling_group
	runs the test 'test_create_scaling_group'

Options:
----------
cafe-runner autoscale dev -p functional (runs all functional tests)
cafe-runner autoscale dev -p system -t speed=quick (runs all quick system tests)
cafe-runner autoscale dev -p system -t speed=slow (runs all system tests that require servers to build to active state)
cafe-runner autoscale dev -p system -t type=lbaas (runs load balancer intergration tests)
cafe-runner autoscale dev -p system -t type=repose (runs repose integration tests)
cafe-runner autoscale dev -p system -t type=rbac (runs rbac integration tests)
cafe-runner autoscale dev -p system -t type=one-time (runs system tests, that are not intended to be run frequently in production)

cafe-runner autoscale dev -m test_delete_all -t groups (deletes all the groups on the account)
cafe-runner autoscale dev -m test_delete_all -t servers (deletes all the servers on the account)
cafe-runner autoscale dev -m test_delete_all -t lbaas (deletes all the nodes on the load balancers)
