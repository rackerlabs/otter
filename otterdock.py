#!/usr/bin/env python

from __future__ import print_function

import os
import StringIO
import subprocess
from sys import exit
import time

from shipper import Shipper, command, run

# Notice the replacements that happen for pip install commands
# This allows quick docker builds and makes sure reqs stay in sync
DOCKERFILE = """FROM ubuntu:12.04

# CloudCafe
ENV SUDO_USER root
ENV HOME /root

{pip_mirror}

# The build process isn't a real tty
ENV DEBIAN_FRONTEND noninteractive

# Use the Rackspace mirrors, they're usually much faster
RUN echo "deb http://mirror.rackspace.com/ubuntu/ precise main restricted universe" > /etc/apt/sources.list
RUN echo "deb http://mirror.rackspace.com/ubuntu/ precise-updates main restricted universe" >> /etc/apt/sources.list
RUN apt-get update
RUN apt-get install -y build-essential git python-dev libxml2-dev libxslt1-dev python-pip python-virtualenv subunit
# requirements
RUN pip install {reqs}
# Dev requirements
RUN pip install {devreqs}

{otter}
WORKDIR /opt/otter

# Expose the otter port and set a default command
EXPOSE 9000
CMD ["make", "run_docker"]
"""

PYTHONPATHS = [
    '/opt/otter',
    '/opt/otter/autoscale_cloudcafe',
    '/opt/otter/autoscale_cloudroast'
]


s = Shipper()


def get_dockerfile(dev=True, pip_mirror=None):
    """
    Formats base Dockerfile string with values, and returns a file handle
    whose contents are the formatted Dockerfile.
    """
    kwargs = {}
    with open('requirements.txt') as f:
        kwargs['reqs'] = " ".join([line.strip() for line in f.readlines()])
    with open('dev_requirements.txt') as f:
        kwargs['devreqs'] = " ".join([line.strip() for line in f.readlines()])

    if dev:
        kwargs['otter'] = 'VOLUME ["/opt/otter"]'
    else:
        kwargs['otter'] = 'ADD . /opt/otter'

    if pip_mirror is not None:
        kwargs['pip_mirror'] = (
            '# Use our PyPi mirror\n'
            'ENV PIP_INDEX_URL {0}'.format(pip_mirror))
    else:
        pip_mirror = ''

    return StringIO.StringIO(DOCKERFILE.format(**kwargs))


# Not required in latest docker-py master
def format_docker_env(env_dict):
    return ['{0}={1}'.format(k, v) for k, v in env_dict.items()]


@command
def start_cassandra(dev=True):
    """
    Starts Cassandra if it hasn't been started with that tag already and
    returns the running container's IP
    """
    with open('schema/__version__') as f:
        schema_version = f.readlines()[0].strip()

    # terrible hack to get the schema version in the command
    command = '/opt/cassandra/bin/cassandra -f > {0}.txt'.format(
        schema_version)
    cass = s.containers(image="cassandra", command=command)

    if len(cass) == 0:
        cass = s.run(
            image='cassandra',
            command=command,
            hostname='cassandra')
        if len(cass) == 0:
            print("Cassandra failed to start")
            exit(1)

        cass_ip = s.inspect(cass[0])[0]['NetworkSettings']['IPAddress']

        # wait until cassandra is listening
        schema = None
        for i in range(10):
            if schema is None:
                schema = run_otter(cass_ip, 'make load-dev-schema', dev=dev)
            else:
                s.start(schema)

            if s.wait(schema)[0][1]['StatusCode'] == 0:
                print("Successfully loaded schema version {0}".format(
                    schema_version))
                return cass_ip
            else:
                time.sleep(5)

        print("Unable to connect to cassandra after 50 seconds")
        exit(1)
    else:
        return s.inspect(cass[0])[0]['NetworkSettings']['IPAddress']




@command
def build_java():
    s.build(
        tag='java',
        path="docker/java"
    )


@command
def build_cassandra():
    s.build(
        tag='cassandra',
        path="docker/cassandra"
    )


@command
def build_otter(sha="dev",
                pip_mirror='http://pypi0.prod.ord.as.rax.io:3145/pypi'):
    s.build(
        tag='otter:{0}'.format(sha),
        fobj=get_dockerfile(dev=(sha == 'dev'), pip_mirror=pip_mirror)
    )


@command
def build_all(sha="dev",
              pip_mirror='http://pypi0.prod.ord.as.rax.io:3145/pypi'):
    build_java()
    build_cassandra()
    build_otter(sha, pip_mirror)


@command
def run_otter(cass_ip, command, dev=True, volumes=None):
    """
    Starts up an otter container with the provided volumes, pointing to a
    particular cassandra host
    """
    otter_env = format_docker_env({
        'CASSANDRA_HOST': cass_ip,
        'PYTHONPATH': ":".join(PYTHONPATHS)
    })

    if dev:
        if volumes is None:
            volumes = ['/mnt/shared/otter:/opt/otter']
        else:
            volumes.append('/mnt/shared/otter:/opt/otter')

    container_id = s.run(
        image='otter:dev',
        command=command,
        environment=otter_env,
        volumes=volumes
    )

    if len(container_id) == 0:
        print("Otter failed to start")
        exit(1)

    return container_id[0]


def make_logdir(log_dir, prefix):
    """
    Creates a log directory in which logs are kept.  Store it in the folder
    [prefix]-<timestamp>
    """
    folder = os.path.expanduser(os.path.join(
        log_dir, prefix, time.strftime("%Y-%m-%d_%H.%M.%S")))
    if not os.path.exists(folder):
        os.makedirs(folder)
    return folder


@command
def unit_tests(dev=True, log_dir="_docker_logs"):
    """
    Run unit tests, and copy the logs over if this is not the dev
    """
    cass_ip = start_cassandra(dev)
    container = run_otter(cass_ip, 'make unit')
    subprocess.call(["docker", "attach", container.id])
    exit_code = s.wait(container)
    if not dev and log_dir is not None:
        try:
            folder = make_logdir(log_dir, "unit_tests")
            subprocess.call([
                "docker", "cp",
                "{0}:/opt/otter/_trial_temp".format(container.id),
                folder])
        except:
            import traceback
            traceback.print_exc()
            print("Unable to copy logs")

    exit(exit_code[0][1]['StatusCode'])


@command
def start(dev=True, run_tag=None, log_dir="/mnt/shared/docker_logs"):
    volumes = None
    if log_dir is not None:
        volumes = ['{0}:/opt/logs'.format(log_dir)]

    run_otter('make run_otter', run_tag, volumes=volumes)


@command
def run_tests(dev=True, run_tag="dev", log_dir="/mnt/shared/docker_logs"):
    volumes = None
    if log_dir is not None:
        volumes = ['{0}:/opt/logs'.format(log_dir)]

    run_otter('make tests', run_tag, volumes=volumes)


@command
def ps(all=False, running=True):
    print(s.containers(pretty=True, all=all, running=running))

run()
