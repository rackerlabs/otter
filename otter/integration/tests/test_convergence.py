"""Tests covering foreseen or known edge cases for the Convergence subsystem.
Tests covering self-healing should be placed in a separate test file.
"""

from twisted.trial.unittest import TestCase

class FailEverything(TestCase):
    def test_and_fail(self):
        self.fail("Fail test, jenkins should archive logs")
