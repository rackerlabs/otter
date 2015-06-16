======================
How cURL Commands Work
======================

cURL is a command-line tool that you can use to interact with *REST*
interfaces. cURL lets you to transmit and receive *HTTP* requests and
responses from the command line or a shell script, which enables you to
work with the API directly. It is available for Linux distributions, Mac
OS X, and Windows. For information about cURL, see http://curl.haxx.se/.

To run the cURL request examples shown in this guide, copy each example
from the HTML version of this guide directly to the command line or a
script.

The following command is an example cURL command that provisions a
server with an isolated network::

    $ curl https://dfw.servers.api.rackspacecloud.com/v2/$account/servers \
           -X POST \
           -H "X-Auth-Project-Id: $account" \
           -H "Content-Type: application/json" \
           -H "Accept: application/json" \
           -H "X-Auth-Token: $token" \
           -d '{"server": {"name": "my_server_with_network", "imageRef": "d42f821e-c2d1-4796-9f07-af5ed7912d0e", "flavorRef": "2", "max_count": 1, "min_count": 1, "networks": [{"uuid": "538a112a-34d1-47ff-bf1e-c40639e886e2"}, {"uuid": "00000000-0000-0000-0000-000000000000"}, {"uuid": "11111111-1111-1111-1111-111111111111"}]}}' \
          | python -m json.tool

.. note::
   The carriage returns in the cURL request examples use a backslash
   (``\``) as an escape character. The escape character allows continuation
   of the command across multiple lines. However, do not include the escape
   character in the JSON request body within the cURL command.

The cURL examples in this guide use the following command-line options:

``-d``: Sends the specified data in a **POST** request to the HTTP server. Use
this option to send a JSON request body to the server.

``-H``: Specifies an extra HTTP header in the request. You can specify any
number of extra headers. Precede each header with the ``-H`` option.

Common headers in Rackspace API requests are as follows:

-  ``Content-Type``. Required for operations with a request body.

   Specifies the format of the request body. Following is the syntax for
   the header where *``format``* is ``json``.

   .. code::

       Content-Type: application/format

-  ``X-Auth-Token``. Required. Specifies the authentication token.

-  ``X-Auth-Project-Id``. Optional. Specifies the project ID, which can
   be your account number or another value.

-  ``Accept``. Optional.

   Specifies the format of the response body. Following is the syntax
   for the header where *``format``* is ``json`` (the default)

   .. code::

       Accept: application/format

``-i``: Includes the HTTP header in the output.

``-s``: Specifies silent or quiet mode, which makes cURL mute. No progress or
error messages are shown.

``-T``: Transfers the specified local file to the remote URL.

``-X``: Specifies the request method to use when communicating with the HTTP
server. The specified request is used instead of the default method,
which is **GET**.


.. note::
   For commands that return a response, you can append the following
   code to the command to call json.tool to pretty-print output:

   .. code::

    | python -m json.tool

To use :file:`json.tool`, import the json module. For information about
:file:`json.tool`, see `json — JSON encoder and
decoder <http://docs.python.org/2/library/json.html>`__.

If you run a Python version older than 2.6, import the simplejson module
and use simplejson.tool. For information about simplejson.tool, see
`simplejson — JSON encoder and decoder <http://simplejson.googlecode.com/svn/tags/simplejson-2.0.9/docs/index.html>`__.

If you do not want to pretty-print JSON output, omit this code.


