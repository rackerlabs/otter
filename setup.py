import os
from setuptools import setup

NAME = 'otter'
SCHEMA_DIR = 'schema'


def getPackages(base):
    """
    Recursively find python packages.
    """
    packages = []

    def visit(arg, directory, files):
        if '__init__.py' in files:
            packages.append(directory.replace('/', '.'))

    os.path.walk(base, visit, None)

    return packages

packages = getPackages(NAME)


def getSchema(base):
    """
    Recursively find cql files
    """
    schemas = []

    def visit(arg, directory, files):
        schemas.append(
            (directory.rstrip('/'),
             [os.path.join(directory, filename)
              for filename in files if filename.endswith('.cql')]))

    os.path.walk(base, visit, None)
    return schemas

data_files = getSchema(SCHEMA_DIR)
data_files.append(('otter/rest', ['otter/rest/otter_ascii.txt']))


# If a twisted/plugins directory exists make sure we install the
# twisted.plugins packages.
if os.path.exists('twisted/plugins'):
    packages.append('twisted.plugins')


# This is an incomplete setup definition useful only for
# installation into a virtualenv with terrarium for deployment.
setup(
    name=NAME,
    version='0.0.0',
    packages=packages,
    license="Apache 2.0",
    data_files=data_files,
    scripts=['scripts/load_cql.py', 'otter/partition.py']
)

# Make Twisted regenerate the dropin.cache, if possible.  This is necessary
# because in a site-wide install, dropin.cache cannot be rewritten by
# normal users.
try:
    from twisted.plugin import IPlugin, getPlugins
except ImportError:
    pass
else:
    list(getPlugins(IPlugin))
