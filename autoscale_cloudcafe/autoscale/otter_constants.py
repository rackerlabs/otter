"""
This has the minimums, maximums and defaults used by the otter api
"""


class OtterConstants(object):
    """
    Minimums, maximums and defaults set by/for the otter api
    """
    MAX_MAXENTITIES = 1000
    MAX_COOLDOWN = 86400
    SCHEDULER_INTERVAL = 11
    SCHEDULER_BATCH = 10
    MAX_GROUPS = 1000
    MAX_POLICIES = 1000
    MAX_WEBHOOKS = 1000
    LIMIT_VALUE_ALL = 1000
    LIMIT_UNIT_ALL = 'MINUTE'
    LIMIT_VALUE_WEBHOOK = 10
    LIMIT_UNIT_WEBHOOK = 'SECOND'
