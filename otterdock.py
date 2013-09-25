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

# Expose the otter port

#Add the configuration directory
EXPOSE 9000
{config}
"""

PYTHONPATHS = [
    '/opt/otter',
    '/opt/otter/autoscale_cloudcafe',
    '/opt/otter/autoscale_cloudroast'
]


s = Shipper()


def get_dockerfile(dev=True, config_dir='/opt/configs', pip_mirror=None):
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
        kwargs['config'] = 'VOLUME ["/opt/configs"]'
    else:
        kwargs['otter'] = 'ADD . /opt/otter'
        kwargs['config'] = 'ADD . {0}'.format(config_dir)

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
    returns the running container
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
            hostname='cassandra',
            detailed=True)
        if len(cass) == 0:
            print("Cassandra failed to start")
            exit(1)

        # wait until cassandra is listening
        schema = None
        for i in range(10):
            if schema is None:
                schema = run_otter('make load-dev-schema', dev=dev,
                                   env={'CASSANDRA_HOST': cass[0].ip})
            else:
                s.start(schema)

            if s.wait(schema)[0][1]['StatusCode'] == 0:
                print("Successfully loaded schema version {0}".format(
                    schema_version))
                return cass[0]
            else:
                time.sleep(5)

        print("Unable to connect to cassandra after 50 seconds")
        exit(1)
    else:
        return s.inspect(cass[0])[0]




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
def run_otter(command, dev=True, volumes=None, env=None):
    """
    Starts up an otter container with the provided volumes, pointing to a
    particular cassandra host
    """
    otter_env = {'PYTHONPATH': ":".join(PYTHONPATHS)}
    if env is not None:
        otter_env.update(env)

    if dev:
        if volumes is None:
            volumes = ['/mnt/shared/otter:/opt/otter',
                       '/opt/configs:/opt/configs']
        else:
            volumes.append('/mnt/shared/otter:/opt/otter')
            volumes.append['/opt/configs:/opt/configs']

    container_id = s.run(
        image='otter:dev',
        command=command,
        environment=format_docker_env(otter_env),
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

def copy_from_container(container, container_filepath, dst_folder):
    try:
        subprocess.call([
            "docker", "cp",
            "{0}:{1}".format(container.id, container_filepath),
            dst_folder])
    except:
        import traceback
        traceback.print_exc()
        print("Unable to copy {0} from {1} to {2}".format(
            container_filepath, container, dst_folder))


@command
def unit_tests(dev=True, log_dir="_docker_logs"):
    """
    Run unit tests, and copy the logs over if this is not the dev
    """
    cass = start_cassandra(dev)
    container = run_otter('make unit', env={'CASSANDRA_HOST': cass.ip})
    subprocess.call(["docker", "attach", container.id])
    exit_code = s.wait(container)
    # can't copy files over if dev, because otter is a shared volume
    if not dev and log_dir is not None:
        folder = make_logdir(log_dir, "unit_tests")
        copy_from_container(container, '/opt/otter/_trial_temp', folder)

    exit(exit_code[0][1]['StatusCode'])


@command
def start(dev=True, background=True):
    """
    Start the otter-api
    """
    cass = start_cassandra(dev)

    env = {'HOSTS_TO_WRITE': "cassandra={0}".format(cass.ip)}
    container = run_otter('make run_docker', dev=dev, env=env)
    if not background:
        subprocess.call(["docker", "attach", container.id])
    return container


@command
def run_cloudcafe(cloudcafe_args, dev=True, log_dir="_docker_logs"):
    """
    Runs the cloudcafe tests with the particular arguments.  The kwargs are
    all the kwargs that get passed to starting otter.
    """
    otter = start(dev)
    otter_ip = s.inspect(otter)[0]['NetworkSettings']['IPAddress']
    env = {'HOSTS_TO_WRITE': "otter={0}".format(otter_ip)}
    command = 'cafe-runner autoscale {0}'.format(cloudcafe_args)

    cloudcafe = run_otter(command, dev=dev, env=env)
    subprocess.call(["docker", "attach", cloudcafe.id])
    exit_code = s.wait(cloudcafe)

    if log_dir is not None:
        folder = make_logdir(log_dir, "cloudcafe_tests")
        with open(os.path.join(folder, 'command.txt'), 'wb') as f:
            f.write(command)
        copy_from_container(cloudcafe, "/root/.cloudcafe/logs/autoscale", folder)
        os.rename(os.path.join(folder, "autoscale"),
                  os.path.join(folder, "cloudcafe_logs"))
        copy_from_container(otter, '/var/log/otter-api.log', folder)

    s.stop(otter)
    exit(exit_code[0][1]['StatusCode'])


@command
def ps(all=False, running=True):
    print(s.containers(pretty=True, all=all, running=running))

run()
