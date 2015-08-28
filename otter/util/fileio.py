"""
Effect based file IO
"""

import attr

from effect import TypeDispatcher, sync_performer


@attr.s
class ReadFileLines(object):
    fname = attr.ib()


@attr.s
class WriteFileLines(object):
    fname = attr.ib()
    lines = attr.ib()


@sync_performer
def perform_read_file_lines(disp, intent):
    with open(intent.fname, "r") as f:
        return f.readlines()


@sync_performer
def perform_write_files_lines(disp, intent):
    with open(intent.fname, "w") as f:
        f.writelines(intent.lines)


def get_dispatcher():
    return TypeDispatcher({
        ReadFileLines: perform_read_file_lines,
        WriteFileLines: perform_write_files_lines})
