# otter/base
FROM    ubuntu:12.04

# The build process isn't a real tty
ENV     DEBIAN_FRONTEND noninteractive

# We want to use our own pypi repo
ENV     PIP_INDEX_URL http://pypi.as.rax.io/pypi/

# Nice to have a reliable way to know you're in a container
ENV     DOCKER true

# Install requirements
RUN     echo "deb http://mirror.rackspace.com/ubuntu/ precise main restricted universe" > /etc/apt/sources.list
RUN     echo "deb http://mirror.rackspace.com/ubuntu/ precise-updates main restricted universe" >> /etc/apt/sources.list
RUN     apt-get update
RUN     apt-get -y install build-essential git python-dev libxml2-dev libxslt1-dev python-pip python-virtualenv

# Install slow compiling pip packages
# If the requirements get updated they'll end up overwriting these
# These should be updated if requirements get updated for build speed
RUN     pip install lxml==3.0.1 pyOpenSSL==0.13 twisted==13.1 paramiko==1.10.0
