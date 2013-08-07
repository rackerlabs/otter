"""
The otter REST API implementation.
"""

# Groups, configs, etc. have to be imported else the routes never get loaded

from otter.rest import (groups as _g, configs as _c, policies as _p,
                        webhooks as _w, admin as _a)

groups = _g
configs = _c
policies = _p
webhooks = _w
admin = _a
