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
