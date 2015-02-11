============
Unit Testing
============

Uses Twisted's testing framework, and has 100% code coverage.

Unit tests can be run using **make unit**

===================
Integration Testing
===================
`autoscale_cloudcafe <https://github.com/rackerlabs/otter/autoscale_cloudcafe>`_, is the test driver for the autoscale api and `autoscale_cloudroast <https://github.com/rackerlabs/otter/autoscale_cloudroast>`_, contains the functional, integration and system tests. It can be installed using dev_requirements.txt in `Otter <https://github.com/rackerlabs/otter>`_. It works in tandem with the Open CAFE and Cloud Cafe.

`Open Cafe <https://github.com/stackforge/opencafe>`_ is the core engine that provides a model, a pattern and assorted common tools for building automated tests. It provides its own light weight unittest based runner, however, it is designed to be modular.

`Cloud Cafe <https://github.com/stackforge/cloudcafe>`_ is an implementaion of the Open Cafe and has drivers for the rackspace open sourced products such as Nova, Block storage etc.

-------------
Configuration
-------------

Autoscale Cloudcafe's configurations will be installed at: USER_HOME/.cloudcafe/configs/autoscale/. To use the framework you will need to create/install your own configurations based on the reference configs. You are now ready to:

1. Execute the test cases for autoscale api.
                       or
2. Write entirely new tests in this repository using the CloudCAFE Framework.

------------------------------------
**Test Plan (autoscale_cloudroast)**
------------------------------------

.. toctree::
   :maxdepth: 3

   test_plan

*(This documentation is automatically generated from our code comments.
If this area is empty, please build on your local machine with
dev_requirements.txt)*

-------------
Running Tests
-------------

                        **make integration**

                                 or

         **cafe-runner autoscale CONFIG(minus .config) PARAMS**

Example:
         *cafe-runner autoscale dev -p functional --parallel*    (executes all the autoscale tests under the functional folder, in parallel)

         *cafe-runner autoscale dev -m test_create_scaling_group*     (executes the test 'test_create_scaling_group.py')

-------------------
autoscale_cloudcafe
-------------------

.. toctree::
   :maxdepth: 3

   autoscale

*(This documentation is automatically generated from our code comments.
If this area is empty, please build on your local machine with
dev_requirements.txt)*
