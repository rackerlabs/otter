#!/usr/bin/env python

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
from twisted.internet.defer import (
    DeferredSemaphore, gatherResults, inlineCallbacks)
from twisted.internet.utils import getProcessOutputAndValue


def get_root():
    from test_repo import autoscale
    return autoscale.__path__[0]


def get_cafe_args(packages, modules, excludes):
    excludes = [] if excludes is None else excludes
    if modules:
        proc_args = []
        if packages:
            proc_args.extend(['-p'] + packages)
        return [proc_args + ['-m', module]
                for module in modules if module not in excludes]
    else:
        return [['-p', package, '-m', module] for package in packages
                for module in get_test_modules(get_root(), package)
                if module not in excludes]


@inlineCallbacks
def run(packages, modules, other_args, reactor, limit, excludes):
    sem = DeferredSemaphore(limit)
    proc_argss = get_cafe_args(packages, modules, excludes)
    deferreds = [
        sem.run(getProcessOutputAndValue, 'cafe-runner',
                other_args + proc_args, env=os.environ, reactor=reactor)
        for proc_args in proc_argss]
    results = yield gatherResults(deferreds, consumeErrors=True)

    failed = False
    for proc_args, (stdout, stderr, code) in zip(proc_argss, results):
        if code == 0:
            continue
        failed = True
        print('Error when running ', ' '.join(proc_args))
        print('Stdout\n', stdout, 'Stderr\n', stderr)

    if failed:
        raise SystemExit('Some tests failed')


def get_python_test_modules(root):
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        for filename in filenames:
            if filename.startswith("test_") and filename[-3:] == ".py":
                yield filename[:-3]


def find_dir(root, _dir):
    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.split(dirpath)[1] == _dir:
            return dirpath


def get_test_modules(root, package):
    mod_dir = find_dir(root, package)
    return get_python_test_modules(mod_dir)


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
        '-m', dest='module', nargs='+',
        help='module pattern as in cafe-runner')
    parser.add_argument(
        '-p', dest='package', nargs='+', help='package as in cafe-runner.')
    parser.add_argument(
        '-e', '--exclude', dest='exclude', nargs='+',
        help='Exclude modules from running')
    parser.add_argument(
        '-l', dest='limit', type=int, default=10,
        help='Number of maximum processes at a time')

    parsed, others = parser.parse_known_args(args)
    if not (parsed.package or parsed.module):
        raise SystemExit("Need at least one of --package or --module")
    d = run(parsed.package, parsed.module, others[1:], reactor,
            parsed.limit, parsed.exclude)
    print('Running all tests')
    call = print_dots(reactor)
    return d.addCallback(lambda _: call.stop())


if __name__ == '__main__':
    task.react(main, (sys.argv,))
