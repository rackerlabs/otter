=============
Documentation
=============

Sphinx is used for document generation, so all docs should be formatted in the `reStructuredText format <http://sphinx.pocoo.org/rest.html#explicit-markup>`_.

Documentation should be placed in the ``docs`` directory of the project, and should mostly exclude the API docs, since that will be automatically generated with `sphinx-apidoc <http://sphinx.pocoo.org/man/sphinx-apidoc.html>`_.

There is no enforcement that non-docstring documentation be updated except by code review.

=======================
Python Coding Standards
=======================

----------
Docstrings
----------
**Enforcement:** a subset of the `pep257 checker <https://github.com/halst/pep257>`_

Every exported module, class, and method must have a docstring explaining what it's for, how to use it, requirements, etc, and should follow the `pep257 docstring conventions <http://www.python.org/dev/peps/pep-0257/>`_.

However (some of these are not defined in `pep257 docstring conventions <http://www.python.org/dev/peps/pep-0257/>`_ but are enforced by the `pep257 checker <https://github.com/halst/pep257>`_:

#. No distinction is made between the formatting of one-line docstrings and multiline docstrings.  All docstrings should open with a triple double-quote (""") on a single line, and end with the same.
#. No newline before the closing """ is necessary.
#. Ending punctuation is not enforced
#. Voice is not enforced

In addition, docstrings should be formatted in `reStructuredText format <http://sphinx.pocoo.org/rest.html#explicit-markup>`_ for Sphinx.  API docs will
be auto-generated with Sphinx.  Please see a `full code example <http://packages.python.org/an_example_pypi_project/sphinx.html#full-code-example>`_ for how to specify variables, parameters, and return values in a docstring.

To check your docstring formatting, please use `make apidoc` to see if there are any Sphinx build errors.

----
Pep8
----
**Enforcement:** `pep8 checker <https://github.com/jcrocholl/pep8>`_

Python code should conform to `pep8 coding standards <http://www.python.org/dev/peps/pep-0008/>`_.  Some highlights:
#. variables, method names, and class names should not be camel-cased, but should have underscores
#. indentation should consist of 4 spaces
#. there should be 1 line between method definitions and 2 lines between class/function definitions
#. code, comments, and docstrings should be wrapped at 80 columns
#. no trailing whitespace

--------
Pyflakes
--------
**Enforcement:** the `pyflakes checker <http://pypi.python.org/pypi/pyflakes>`_

Please do not:
#. import modules that are not needed in the code, or import the same modules more than once
#. declare unused variables

-----
Other
-----
Please limit 1 letter variable names (e.g. using 'i' within a for loop is OK.  Passing around a 'q' object as part of an interface method is not).  There is no linter to enforce this policy - this will just be enforced through code review.

=======
Testing
=======

#. Try to go for 100% unit test coverage (use the ``coverage`` tool to check - run ``make coverage``)
#. Run tests using twisted trial for testing using deferreds (use ``twisted.trial.unittest`` instead of ``unittest`` or ``unittest2``)
#. test modules, classes, and methods should also all have docstrings explaining the test
#. each test method should try to limit the scope of testing (like how experiments should only test 1 variable at a time)
#. mocking in tests

  #. patching should be reverted after every test case (in teardown)
  #. mock in the right place (if you import X from Y, mock Y.X, not X)
  #. Autospec/specify the spec unless you have a good reason not to (see http://www.voidspace.org.uk/python/mock/helpers.html#autospeccing), so your tests do not pass by accident (e.g. when a mock evaluates to true, or when calling assert_X just calls a mock rather than the actually assert method).

#. unit tests shouldn't depend on the state of the previous test case, and hence should be run in random order (``trial --random 0 tests``, or ``make unit``)
#. integration tests on dev machine - would be nice to limit number of services that need to be run at once

  #. mocking other rackspace REST services (http://sourceforge.net/p/soaprest-mocker/wiki/Home/, http://fog.io/#.6.0/compute/, or we can write our own)

=======
Metrics
=======
#. Use metric library `yunomi <https://github.com/richzeng/yunomi>`_ for timers, histograms, etc.
#. Anything that makes or accepts RPC or http requests should include support for tracing headers: a trace id, a span id, and a parent span id.  Can use the `tryfer python client library <https://github.com/racker/tryfer>`_

=============
Build process
=============
*(work in progress)*

#. Merges trigger tests and would be nice if it could trigger auto re-generation of API docs.

=============================
Partial code review checklist
=============================
*(work in progress)*

These are just some suggested items other than checking that the code actually does what it should.

#. Do tests pass?
#. Do the tests cover enough of the code (not just from running coverage - make sure that they cover enough cases)?
#. Are the test cases well-written (limited in scope and mocking done correctly, etc.)?
#. Are all public modules/classes/interfaces/methods/attributes documented?
#. If code changes functionality, has the corresponding documentation (both docstrings and non-docstring documentation) be updated to reflect this change?
#. Are public classes/modules/methods/variables sensibly named (are they reasonably descriptive)?
#. Are failure cases either handled or documented?
#. Is the code readable?
