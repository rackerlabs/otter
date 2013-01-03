""" CQL Batch wrapper"""


class Batch:
    """ CQL Batch wrapper"""
    def __init__(self, statements, params, consistency='ONE',
                 timestamp=None):
        self.statements = statements
        self.params = params
        self.consistency = consistency
        self.timestamp = timestamp

    def _generate(self):
        str = 'BEGIN BATCH USING CONSISTENCY '
        str += self.consistency + ' '
        if self.timestamp is not None:
            str += 'AND WITH TIMESTAMP {} '.format(self.timestamp)
        str += ' '.join(self.statements)
        str += ' APPLY BATCH;'
        return str

    def execute(self, client):
        """
        Execute the CQL batch against the given client object
        """
        return client.execute(self._generate(), self.params)
