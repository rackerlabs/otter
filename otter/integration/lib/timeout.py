class TimeoutError(Exception):
    """This exception will raise when an operation exceeds a maximum amount
    of time without showing any progress.
    """
