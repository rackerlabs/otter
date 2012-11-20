import os
from setuptools import setup

NAME='otter'

def getPackages(base):
    packages = []

    def visit(arg, directory, files):
        if '__init__.py' in files:
            packages.append(directory.replace('/', '.'))

    os.path.walk(base, visit, None)

    return packages


packages = getPackages(NAME)
if os.path.exists('twisted/plugins'):
    packages.append('twisted.plugins')


setup(
    name=NAME,
    version='0.0.0',
    packages=packages
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
