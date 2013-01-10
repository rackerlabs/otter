"""
The otter REST API implementation.
"""

# Groups, configs, etc. have to be imported else the routes never get loaded

from otter.rest import groups as _g, configs as _c

groups = _g
configs = _c
