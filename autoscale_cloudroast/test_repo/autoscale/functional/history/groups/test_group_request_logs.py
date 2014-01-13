"""
Test the request.* event types for scaling groups.
Note: Only requests that do not trigger convergence events are tested in this file.
"""
class HistoryGroupRequestsTest(AutoscaleFixture):
    """
    Verfiy that request event types associated with scaling groups are correctly recorded in the
    history audit log.
    """

