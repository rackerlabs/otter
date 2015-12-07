.. _how-curl-commands-work:

cURL is a command-line tool that you can use to interact with REST interfaces. cURL lets
you transmit and receive HTTP requests and responses from the command line or a shell
script, which enables you to work with the API directly. cURL is available for Linux
distributions, Mac OS® X, and Microsoft Windows®. For information about cURL, see
`http://curl.haxx.se/ <http://curl.haxx.se/>`__.

To run the cURL request examples shown in this guide, copy each example from the HTML version
of this guide directly to the command line or a script.

.. _auth-curl-json:

The following example shows a cURL command for sending an authentication request to
the Rackspace Cloud Identity service.

**cURL command example: JSON request**

.. include:: ../common-gs/samples/auth-req-curl.rst

In this example, ``$apiKey`` is an environment variable that stores your API key value.
Environment variables make it easier to reference account information in API requests,
to reuse the same cURL commands with different credentials, and also to keep sensitive
information like your API key from being exposed when you send requests to Rackspace
Cloud API services. For details about creating environment variables, see :ref:`Configure
environment variables <configure-environment-variables>`.

..  note::

    The carriage returns in the cURL request examples use a backslash (``\``) as an
    escape character. The escape character allows continuation of the command across
    multiple lines.


The cURL examples in this guide use the following command-line options.

+-----------+-----------------------------------------------------------------------+
| Option    | Description                                                           |
+===========+=======================================================================+
| **-d**    | Sends the specified data in a **POST** request to the HTTP server.    |
|           | Use this option to send a JSON request body to the server.            |
+-----------+-----------------------------------------------------------------------+
| **-H**    | Specifies an extra HTTP header in the request. You can specify any    |
|           | number of extra headers. Precede each header with the ``-H`` option.  |
|           |                                                                       |
|           | Common headers in Rackspace API requests are as follows:              |
|           |                                                                       |
|           |                                                                       |
|           | ``Content-Type``: Required for operations with a request body.        |
|           |                                                                       |
|           | - Specifies the format of the request body. Following is the syntax   |
|           |   for the header where format is ``json``:                            |
|           |                                                                       |
|           |   .. code::                                                           |
|           |                                                                       |
|           |      Content-Type: application/json                                   |
|           |                                                                       |
|           | ``X-Auth-Token``: Required.                                           |
|           |                                                                       |
|           | - Specifies the authentication token.                                 |
|           |                                                                       |
|           | ``X-Auth-Project-Id``: Optional.                                      |
|           |                                                                       |
|           | - Specifies the project ID, which can be your account number or       |
|           |   another value.                                                      |
|           |                                                                       |
|           | ``Accept``: Optional.                                                 |
|           |                                                                       |
|           | - Specifies the format of the response body. Following is the syntax  |
|           |   for the header where the format is ``json``, which is the           |
|           |   default:                                                            |
|           |                                                                       |
|           |   .. code::                                                           |
|           |                                                                       |
|           |      Accept: application/json                                         |
|           |                                                                       |
|           |                                                                       |
+-----------+-----------------------------------------------------------------------+
| **-i**    | Includes the HTTP header in the output.                               |
+-----------+-----------------------------------------------------------------------+
| **-s**    | Specifies silent or quiet mode, which makes cURL mute. No progress or |
|           | error messages are shown.                                             |
+-----------+-----------------------------------------------------------------------+
| **-T**    | Transfers the specified local file to the remote URL.                 |
+-----------+-----------------------------------------------------------------------+
| **-X**    | Specifies the request method to use when communicating with the HTTP  |
|           | server. The specified request is used instead of the default method,  |
|           | which is **GET**.                                                     |
+-----------+-----------------------------------------------------------------------+

For commands that return a response, use json.tool to pretty-print the output by
appending the following command to the cURL call:

.. code::

   | python -m json.tool

..  note::

    To use json.tool, import the JSON module. For information about json.tool, see
    `JSON encoder and decoder`_.

    If you run a Python version earlier than 2.6, import the simplejson module and use
    simplejson.tool. For information about simplejson.tool, see
    `simplejson encoder and decoder`_.

    If you do not want to pretty-print JSON output, omit this code.

.. _json encoder and decoder: http://docs.python.org/2/library/json.html
.. _simplejson encoder and decoder: http://simplejson.googlecode.com/svn/tags/simplejson-2.0.9/docs/index.html

.. _json.tool: http://docs.python.org/2/library/json.html
.. _simplejson.tool: http://simplejson.googlecode.com/svn/tags/simplejson-2.0.9/docs/index.html
