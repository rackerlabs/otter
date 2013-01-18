""" CQL Batch wrapper"""

from silverberg.client import ConsistencyLevel


class Batch(object):
    """ CQL Batch wrapper"""
    def __init__(self, statements, params, consistency=ConsistencyLevel.ONE,
                 timestamp=None):
        self.statements = statements
        self.params = params
        self.consistency = consistency
        self.timestamp = timestamp

    def _generate(self):
        str = 'BEGIN BATCH '
        if self.timestamp is not None:
            str += 'USING TIMESTAMP {} '.format(self.timestamp)
        str += ' '.join(self.statements)
        str += ' APPLY BATCH;'
        return str

    def execute(self, client):
        """
        Execute the CQL batch against the given client object
        """
        return client.execute(self._generate(), self.params, self.consistency)
