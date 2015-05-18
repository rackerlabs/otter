"""
Run cafe-runner in multiple processes

Expects -m argument with multiple values. Any other args passed will be
used when invoking cafe-runner
"""
from __future__ import print_function

import os
import sys
from argparse import ArgumentParser

from twisted.internet import task
from twisted.internet.defer import gatherResults, inlineCallbacks
from twisted.internet.utils import getProcessOutputAndValue


@inlineCallbacks
def run(modules, other_args, reactor):
    deferreds = [
        getProcessOutputAndValue(
            'cafe-runner', other_args + ['-m', module], env=os.environ,
            reactor=reactor)
        for module in modules]
    results = yield gatherResults(deferreds, consumeErrors=True)

    failed = []
    for module, (stdout, stderr, code) in zip(modules, results):
        print('Standard out and error when running module', module)
        print(stdout, '\n', stderr)
        if code != 0:
            failed.append(module)

    if failed:
        raise SystemExit('modules {} failed'.format(','.join(failed)))


def print_dot():
    print('.', end='')
    sys.stdout.flush()


def print_dots(clock):
    call = task.LoopingCall(print_dot)
    call.clock = clock
    call.start(1.0)
    return call


def main(reactor, args):
    parser = ArgumentParser(
        description='Run multiple cafe-runner test modules parallely as '
                    'sub-processes. Every argument given here is passed '
                    'to cafe-runner')
    parser.add_argument(
        '-m', dest='module', action='append', required=True,
        help='module pattern as in cafe-runner. Can be given multiple times')
    parsed, others = parser.parse_known_args(args)
    d = run(parsed.module, others[1:], reactor)
    print('Running all tests')
    call = print_dots(reactor)
    return d.addCallback(lambda _: call.stop())


if __name__ == '__main__':
    task.react(main, (sys.argv,))
