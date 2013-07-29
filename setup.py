import os
from setuptools import setup

# When pip installs anything from packages, py_modules, or ext_modules that
# includes a twistd plugin (which are installed to twisted/plugins/),
# setuptools/distribute writes a Package.egg-info/top_level.txt that includes
# "twisted".  If you later uninstall Package with `pip uninstall Package`,
# pip removes all of twisted/ instead of just Package's twistd plugins.  See
# https://github.com/pypa/pip/issues/355
#
# To work around this problem, we monkeypatch
# setuptools.command.egg_info.write_toplevel_names to not write the line
# "twisted".  This fixes the behavior of `pip uninstall Package`.  Note that
# even with this workaround, `pip uninstall Package` still correctly uninstalls
# Package's twistd plugins from twisted/plugins/, since pip also uses
# Package.egg-info/installed-files.txt to determine what to uninstall,
# and the paths to the plugin files are indeed listed in installed-files.txt.
try:
    from setuptools.command import egg_info
    egg_info.write_toplevel_names
except (ImportError, AttributeError):
    pass
else:
    def _top_level_package(name):
        return name.split('.', 1)[0]

    def _hacked_write_toplevel_names(cmd, basename, filename):
        pkgs = dict.fromkeys(
            [_top_level_package(k)
                for k in cmd.distribution.iter_distribution_names()
                if _top_level_package(k) != "twisted"]
        )
        cmd.write_file("top-level names", filename, '\n'.join(pkgs) + '\n')

    egg_info.write_toplevel_names = _hacked_write_toplevel_names

NAME = 'otter'
SCHEMA_DIR = 'schema'


def refresh_plugin_cache():
    # Make Twisted regenerate the dropin.cache, if possible.  This is
    # necessary because in a site-wide install, dropin.cache cannot
    # be rewritten by normal users.
    try:
        from twisted.plugin import IPlugin, getPlugins
        list(getPlugins(IPlugin))
    except ImportError:
        pass


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
# data_files.append(('otter/rest', ['otter/rest/otter_ascii.txt']))

# This is an incomplete setup definition useful only for
# installation into a virtualenv with terrarium for deployment.
setup(
    name=NAME,
    version='0.0.0',
    packages=getPackages(NAME) + ['twisted.plugins'],
    license="Apache 2.0",
    data_files=data_files,
    package_data={'twisted': ['plugins/otter_tap.py']},
    scripts=['scripts/load_cql.py']
)

refresh_plugin_cache()
