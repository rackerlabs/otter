#!/usr/bin/env python

from sys import exit
from shipper import *
import StringIO

# Notice the replacements that happen for pip install commands
# This allows quick docker builds and makes sure reqs stay in sync
DOCKERFILE_DEV = """FROM ubuntu:12.04

# CloudCafe
ENV SUDO_USER root
ENV HOME /root

# Use our PyPi mirror
ENV PIP_INDEX_URL http://pypi0.prod.ord.as.rax.io:3145/pypi

# The build process isn't a real tty
ENV DEBIAN_FRONTEND noninteractive

# Use the Rackspace mirrors, they're usually much faster
RUN echo "deb http://mirror.rackspace.com/ubuntu/ precise main restricted universe" > /etc/apt/sources.list
RUN echo "deb http://mirror.rackspace.com/ubuntu/ precise-updates main restricted universe" >> /etc/apt/sources.list
RUN apt-get update
RUN apt-get install -y build-essential git python-dev libxml2-dev libxslt1-dev python-pip python-virtualenv
# Dev requirements
RUN pip install {0}
# requirements
RUN pip install {1}

VOLUME ["/opt/otter"]
WORKDIR /opt/otter

# Expose the otter port and set a default command
EXPOSE 9000
CMD ["make", "run_docker"]
"""

PYTHONPATH = ":".join([
    '/opt/otter',
    '/opt/otter/autoscale_cloudcafe',
    '/opt/otter/autoscale_cloudroast'
])

# Not required in latest docker-py master
def format_docker_env(env_dict):
    return ['{0}={1}'.format(k, v) for k, v in env_dict.items()]

@command
def start():
    s = Shipper()
    cass = s.run(
        image='cassandra',
        command='/opt/cassandra/bin/cassandra -f',
        hostname='cassandra',
        once=True
    )
    cass_ip = s.inspect(cass[0])[0]['NetworkSettings']['IPAddress']
    otter_env = format_docker_env({
        'CASSANDRA_HOST': cass_ip,
        'PYTHONPATH': PYTHONPATH
    })
    otter = s.run(
        image='otter:dev',
        command='make run_docker',
        environment=otter_env,
        volumes=['/mnt/shared/otter:/opt/otter'],
        once=True
    )
    print(otter)

@command
def build():
    with open('requirements.txt') as f:
        reqs = " ".join([line.strip() for line in f.readlines()])
    with open('dev_requirements.txt') as f:
        devreqs = " ".join([line.strip() for line in f.readlines()])

    dockerfile = StringIO.StringIO(DOCKERFILE_DEV.format(devreqs, reqs))
    s = Shipper()
    s.build(
        tag='otter:dev',
        fobj=dockerfile
    )

@command
def run_tests():
    s = Shipper()
    cass = s.run(
        image='cassandra',
        command='/opt/cassandra/bin/cassandra -f',
        hostname='cassandra',
        once=True
    )
    try:
        cass = cass[0]
    except IndexError:
        print("Cassandra failed to start")
        exit(1)
    cass_ip = s.inspect(cass)[0]['NetworkSettings']['IPAddress']
    otter_env = format_docker_env({
        'CASSANDRA_HOST': cass_ip,
        'PYTHONPATH': PYTHONPATH
    })
    s.run(
        image='otter:dev',
        command='make test',
        environment=otter_env,
        volumes=['/mnt/shared/otter:/opt/otter'],
        once=True
    )

run()
