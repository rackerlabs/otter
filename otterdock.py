#!/usr/bin/env python

from __future__ import print_function

from sys import exit
from shipper import Shipper, command, run
import StringIO

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
RUN apt-get install -y build-essential git python-dev libxml2-dev libxslt1-dev python-pip python-virtualenv
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


def get_dockerfile(dev=True, otter_logs=None,
                   pip_mirror='http://pypi0.prod.ord.as.rax.io:3145/pypi'):
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
def start_cassandra(run_tag="dev"):
    """
    Starts Cassandra if it hasn't been started with that tag already and
    returns the running container's IP
    """
    cass = s.run(
        image='cassandra',
        command='RUN_REASON={0} /opt/cassandra/bin/cassandra -f'.format(
            run_tag),
        hostname='cassandra',
        once=True)
    if len(cass) == 0:
        print("Cassandra failed to start")
        exit(1)

    return s.inspect(cass[0])[0]['NetworkSettings']['IPAddress']


@command
def build():
    s.build(
        tag='otter:dev',
        fobj=get_dockerfile()
    )


@command
def run_otter(command, run_tag="dev", pythonpaths=None, volumes=None):
    cass_ip = start_cassandra(run_tag)

    if pythonpaths is None:
        pythonpaths = PYTHONPATHS
    else:
        pythonpaths = PYTHONPATHS + pythonpaths

    otter_env = format_docker_env({
        'CASSANDRA_HOST': cass_ip,
        'PYTHONPATH': ":".join(pythonpaths)
    })

    if run_tag == "dev":
        if volumes is None:
            volumes = ['/mnt/shared/otter:/opt/otter']
        else:
            volumes.append('/mnt/shared/otter:/opt/otter')

    container_id = s.run(
        image='otter:dev',
        command=command,
        environment=otter_env,
        volumes=volumes,
        once=True
    )

    if len(container_id) == 0:
        print("Otter failed to start")
        exit(1)

    return container_id[0]


@command
def start(run_tag="dev"):
    container_id = run_otter('make run_otter', run_tag)


@command
def unit_tests(run_tag="dev"):
    container_id = run_otter('make unit', run_tag)


@command
def run_tests(run_tag="dev"):
    container_id = run_otter('make test', run_tag)


@command
def ps(all=False, running=True):
    print(s.containers(pretty=True, all=all, running=running))

run()
