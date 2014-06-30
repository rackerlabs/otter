"""
Tests for a SQL-backed otter store.

This uses an in-memory SQLite database, instead of canned
responses. Canned responses would be really easy to get wrong, leading
to useless tests. Furthermore, in-memory SQLite is plenty fast to be
useful as tests.

"""

from alchimia import TWISTED_STRATEGY as STRATEGY
from otter.models import interface, sql
from sqlalchemy import create_engine
from twisted.internet import reactor
from twisted.trial.unittest import TestCase
from zope.interface.verify import verifyObject


def log(*a, **kw):
    """FIXME! DO SOMETHING USEFUL HERE.

    The interfaces fail to document what they want from me.
    """


def _create_sqlite(_reactor=reactor):
    return create_engine("sqlite://", reactor=_reactor, strategy=STRATEGY)


class SQLiteTestMixin(object):
    """
    A test mixin that sets up an asynchronous, in-memory SQLite
    database, with some alchimia + SQLAlchemy chrome plating.
    """
    def setUp(self):
        self.engine = _create_sqlite()
        return sql.create_tables(self.engine)


class SQLScalingGroupTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL scaling group implementation implements the
        :class:`interface.IScalingGroup` interface.
        """
        group = sql.SQLScalingGroup(self.engine)
        verifyObject(interface.IScalingGroup, group)


class SQLScalingScheduleCollectionTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL scaling schedule collection implementation implements the
        :class:`interface.IScalingScheduleCollection` interface.
        """
        sched_coll = sql.SQLScalingScheduleCollection(self.engine)
        verifyObject(interface.IScalingScheduleCollection, sched_coll)


class SQLScalingGroupCollectionTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL scaling group collection implementation implements the
        :class:`interface.IScalingGroupCollection` interface.
        """
        group_coll = sql.SQLScalingGroupCollection(self.engine)
        verifyObject(interface.IScalingGroupCollection, group_coll)


    def test_empty_count(self):
        """
        A scaling group collection has no groups, policies or webhooks.

        FIXME: this actually tests what happens for nonexistant
        tenants... maybe the sql schema can't tell the difference?

        """
        coll = sql.SQLScalingGroupCollection(self.engine)
        d = coll.get_counts(log, "tenant")

        d.addCallback(self.assertEqual, {"groups": 0,
                                         "policies": 0,
                                         "webhooks": 0})
        return d


class SQLAdminTests(SQLiteTestMixin, TestCase):
    def test_interface(self):
        """
        The SQL admin interface implementation implements the
        :class:`interface.IAdmin` interface.
        """
        admin = sql.SQLAdmin(self.engine)
        verifyObject(interface.IAdmin, admin)
