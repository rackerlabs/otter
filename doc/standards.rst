=======================
Documentation Standards
=======================

Sphinx is used for document generation, so all docs should be formatted in the `reStructuredText format
<http://sphinx.pocoo.org/rest.html#explicit-markup>`_.

Documentation should be placed in the ``docs`` directory of the project, and should mostly exclude the
API docs, since that will be automatically generated with `sphinx-apidoc
<http://sphinx.pocoo.org/man/sphinx-apidoc.html>`_.

There is no enforcement that non-docstring documentation be updated except by code review.

=======================
Python Coding Standards
=======================

----------
Docstrings
----------
**Enforcement:** a subset of the `pep257 checker <https://github.com/halst/pep257>`_

Every exported module, class, and method must have a docstring explaining what it's for, how to use it,
requirements, etc, and should follow the `pep257 docstring conventions
<http://www.python.org/dev/peps/pep-0257/>`_.

However (some of these are not defined in `pep257 docstring conventions
<http://www.python.org/dev/peps/pep-0257/>`_ but are enforced by the `pep257
checker <https://github.com/halst/pep257>`_:

#. No distinction is made between the formatting of one-line docstrings and multiline docstrings.  All
   docstrings should open with a triple double-quote (``"""``) on a single line, and end with the same.
#. No newline before the closing ``"""`` is necessary.
#. Ending punctuation is not enforced
#. Voice is not enforced

In addition, docstrings should be formatted in `reStructuredText format
<http://sphinx.pocoo.org/rest.html#explicit-markup>`_ for Sphinx.  API docs will
be auto-generated with Sphinx.  Please see a `full code example
<http://packages.python.org/an_example_pypi_project/sphinx.html#full-code-example>`_ for how to specify
variables, parameters, and return values in a docstring.

To check your docstring formatting, please use `make apidoc` to see if there are any Sphinx build
errors.

Documenting Exceptions
**********************

Note that since we are using Twisted, the ``:raises:`` keyword implies an asynchronous exception if
the return value is a ``Deferred``. If possible exceptions should be asynchronous in an asynchronous
function.  If the function has a mix of asynchronous and synchronous, the synchronous exceptions should
be explicitly called out.

Test Docstrings
***************

Test docstrings should be stated in a present tense, in the active voice, as opposed to a
`conditional perfect <https://en.wikipedia.org/wiki/Conditional_perfect>`_, passive
voice construction like this sentence.

From `this post <https://plus.google.com/115348217455779620753/posts/YA3ThKWhSAj>`_ on good test case
docstrings:

#. Write the first docstring that comes to mind. It will almost certainly be::

    """Test that input is parsed correctly."""

#. Get rid of "Test that" or "Check that". We know it's a test::

    """Input should be parsed correctly."""

#. Seriously?! Why'd you have to go and add "should"? It's a test, it's all about "should"::

    """Input is parsed correctly."""

#. "Correctly", "properly", and "as we expect" are all redundant. Axe them too::

    """Input is parsed."""

#. Look at what's left. Is it saying anything at all? If so, great. If not, consider adding something specific about the test behaviour and perhaps even why it's desirable behaviour to have::

    """
    Input is parsed into an immutable dict according to the config
    schema, so we get config info without worrying about input
    validation all the time.
    """

----
Pep8
----
**Enforcement:** `pep8 checker <https://github.com/jcrocholl/pep8>`_

Python code should conform to `pep8 coding standards <http://www.python.org/dev/peps/pep-0008/>`_.  Some highlights:

#. variables, method names, and class names should not be camel-cased, but should have underscores
#. indentation should consist of 4 spaces
#. there should be 1 line between method definitions and 2 lines between class/function definitions
#. no trailing whitespace
#. code, comments, and docstrings should be wrapped at 80 columns if possible, but the linter will
   allow lines of up to 105 columns for those lines that really cannot be wrapped (long URLs, for
   example) (which is rounded down from the maximum number of columns will fit into the Github diff
   viewer).


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
Please limit 1 letter variable names (e.g. using 'i' within a for loop is OK.  Passing around a 'q'
object as part of an interface method is not).  There is no linter to enforce this policy - this will
just be enforced through code review.

=======
Testing
=======

We are using Twisted's testing framework, since the codebase is Twisted-based.  So tests are run using
``trial``, and the unit testing framework is :mod:`twisted.trial.unittest` rather than the standard
library ``unittest`` or ``unittest2`` (test cases should be subclasses of
:class:`twisted.trial.unittest.TestCase`).

-----------------------
General test guidelines
-----------------------

#. All tests reside in the main code directory in the subdirectory ``test``.
#. In general, there should be one test module corresponding to each code module.  So for example, if
   in the code directory there is a module ``models`` with submodules ``interface.py`` and ``mock.py``,
   then in the test directory there should be a module ``models`` with submodules ``test_interface.py``
   and ``test_mock.py``
#. Unit tests shouldn't depend on the state of the previous test case, and hence should be run in
   random order (``trial --random 0 test`` to use a random seed, which the ``make unit`` does.  If an
   error is encountered, the same test ordering may be achieved by checking what the random seed that
   was generated was, and running ``trial --random <seed> test``
#. Sometimes it may be easier to debug errors if only a single test case is run.  You can specify any
   module as an argument to ``trial``.  For example:
   ``trial test.submodule.SpecificTestCase.test_specific_test_method``
#. Try to go for 100% unit test coverage where applicable.  ``make coverage`` will run Ned Batchelder's
   ``coverage`` package on the unit test results.  Sometimes the coverage results will not show 100% -
   e.g. on interface definitions, ``pass`` in the method definitions will not be covered.  That's fine.
#. Test modules, classes, and methods should also all have docstrings explaining the test.
#. Each test method should try to limit the scope of testing (like how experiments should only test 1
   variable at a time)
#. Each test's equality assertions should follow the convention of (observed, expected).

------------------
Mocking guidelines
------------------

Limiting the scope of the testing often involves mocking modules, classes, or functions.  We use
Michael Foord's `mock package <http://www.voidspace.org.uk/python/mock/>`_ to do so - it has extensive
documentation.  Here are a couple more suggestions:

#. If patching needs to happen, it should be in ``setUp`` should be reverted in in ``tearDown`` and
   the right dependency should be patched:  (i.e. if you import X from Y, mock Y.X, not X)
#. Dependency injection is preferred over patching.
#. Autospec/specify the spec unless you have a good reason not to (see
   http://www.voidspace.org.uk/python/mock/helpers.html#autospeccing), so your tests do not pass by
   accident (e.g. when a mock evaluates to true, or when calling assert_X just calls a mock rather than
   the actually assert method)

----------------------------
Interface testing guidelines
----------------------------

By "interface" in this section we mean the interaction point between two parts of this system, or the
interaction between the user and this system, or this system and another system.

**Testing code dependant upon an interface**: In general, code should not rely on particular
implementations of an interface.  When mocking the depency, only the the parts specified by the
interface should be mocked.  If the dependant code uses anything other than what is specified by the
interface, the tests should fail.

**Testing implementations of an interface**: Some generalized code that tests implementation of a
particular interface would be also useful, so it can be used to test all implementations.

**JSON Schema**:  Output in JSON format can be tested via `jsonschema
<https://github.com/Julian/jsonschema>`_, to ensure that it matches what is specified in the interface

**Zope.Interface**: `zope.interface <http://docs.zope.org/zope.interface/README.html>`_, is a library
used to explicitly state the interface between two internal parts of the system. You can verify that
something has implemented the interface by calling ``zope.interface.verifyObject()`` on the interface
and the implementation.

-----------------------------------
Twisted-specific testing guidelines
-----------------------------------

Testing Twisted involves some quirks, most of which are covered in the `Twisted testing documentation
<http://twistedmatrix.com/documents/current/core/howto/testing.html>`_.

Here are several other guidelines for testing Twisted code:

**Test Logs**:

When using trial all log messages end up in _trial_temp/test.log. The fully qualified name of the test
case is helpfully logged prior to running that test so you can easily search this file for logs related
to a specific test.  Example::

   2012-05-10 18:17:07+0000 [-] --> test.provider.test_node.SetMetadataTest.test_publish_success <--

**Testing things that take time**:

If testing code that requires interaction with :func:`time.time()`, to make the tests faster (and to
make things easier to test), you can patch :func:`time.time` with :func:`twisted.task.Clock.seconds`
(`Clock docs <http://twistedmatrix.com/documents/12.1.0/api/twisted.internet.task.Clock.html>`_). Then
if you want to simulate time passing, you can call ``clock.advance(X)`` to 'advance' the clock by _x_
seconds, rather than ``time.sleep(X)``. The clock can be also used as a replacement for the reactor in
certain places (for instance, wherever ``reactor.callLater`` is used, or in ``LoopingCall``, or
wherever ``reactor.seconds()`` is used).

For example, in this test the clock is advanced 8 seconds, to test the code executed has indeed been
timed as >= 8 seconds.

**Testing things that return deferreds**:

While :class:`Deferred` objects can be returned from test methods, it's better to test only your
:class:`Deferred` generation code rather than also depending on the reactor spinning (which is what
happens when a :class:`Deferred` is returned from a test method in ``trial``).

If it is possible to do so, instrument everything in the test to return immediately, and then in the
test after you get your :class:`Deferred`, assert that the :class:`Deferred` has already fired. Then
run the tests on the result of that :class:`Deferred`.

In :mod:`test.utils`, three methods are provided to help test :class:`Deferred` code:
:meth:`test.utils.DeferredTestingMixin.assert_deferred_succeeded`, and
:meth:`test.utils.DeferredTestingMixin.assert_deferred_failed`.

Obviously, if you cannot completely patch everything in your test, just go ahead and return the
:class:`Deferred` from the test case.

**Logging errors in Twisted**

If you have logged any errors or failures in your code, :class:`twisted.trial.unittest.TestCase` stores
each error logged during the run of the test and reports them as errors during the cleanup phase (after
``tearDown``).  At the end of a test case where errors were logged,
:meth:`twisted.trial.unittest.TestCase.flushLoggedErrors` should be called with the errors that were
expected to have been logged.

(See `similar guidelines for warnings
<http://twistedmatrix.com/documents/current/core/howto/testing.html#auto5>`_)

-------------------
Integration Testing
-------------------
#. Some limited integration-y tests exist in ``otter.test.unitgration``, but these may be removed.
#. `cloudcafe tests <https://github.com/rackerlabs/autoscale_cloudcafe>`_ for autoscale can currently
   be run from the dev VM.  It currently does not attempt to scale up, but eventually it would be nice
   to limit the services that ene to be spun up.
#. TBD: mocking other rackspace REST services (http://sourceforge.net/p/soaprest-mocker/wiki/Home/,
   http://fog.io/#.6.0/compute/, or we can write our own)

=======
Metrics
=======
#. Use metric library `yunomi <https://github.com/richzeng/yunomi>`_ for timers, histograms, etc.
#. Anything that makes or accepts RPC or http requests should include support for tracing headers: a
   trace id, a span id, and a parent span id.  Can use the `tryfer python client library
   <https://github.com/racker/tryfer>`_

=======
Logging
=======

#. Use the bound twisted logger :data:`otter.log.log`, which is an instance of
   :class:`otter.log.bound.BoundLog`
#. The bound log should be passed down the call stack so that structured data can be passed along.
   Bind more structured data by doing the following::

    def some_function(log, *args, **kwargs):
        further_bound_log = log.bind(system="the logging facility",
                                     user_id="some user id")
        some_other_function(further_bound_log)

#. Log failure objects with the ``err`` function::

    def _errback(failure):
        log.err(failure)

    d = do_something()
    d.addErrback(_errback)


=============
Build process
=============
#. The Github Pull-Request Builder plugin for jenkins builds the latest commit to all open pull requests
   by first merging it into master, then running all the unit tests and linters on it.  If a build
   fails to pass tests or linting, the pull request is marked as unsafe to merge.
#. The build also builds these Sphinx docs every time.
#. Automated integration tests TBD

=============================
Partial code review checklist
=============================
*(work in progress)*

These are just some suggested items other than checking that the code actually does what it should.

#. Do tests pass?
#. Do the tests cover enough of the code (not just from running coverage - make sure that they cover
   enough cases)?
#. Are the test cases well-written (limited in scope and mocking done correctly, etc.)?
#. Are all public modules/classes/interfaces/methods/attributes documented?
#. If code changes functionality, has the corresponding documentation (both docstrings and non-
   docstring documentation) be updated to reflect this change?
#. Are public classes/modules/methods/variables sensibly named (are they reasonably descriptive)?
#. Are failure cases either handled or documented?
#. Is the code readable?
