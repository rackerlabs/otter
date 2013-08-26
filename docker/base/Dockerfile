FROM    ubuntu:12.04

# The build process isn't a real tty
ENV     DEBIAN_FRONTEND noninteractive

# Nice to have a reliable way to know you're in a container
ENV     DOCKER true

# Install requirements
RUN     echo "deb http://mirror.rackspace.com/ubuntu/ precise main restricted universe" > /etc/apt/sources.list
RUN     echo "deb http://mirror.rackspace.com/ubuntu/ precise-updates main restricted universe" >> /etc/apt/sources.list
RUN     apt-get update
RUN     apt-get -y install build-essential git python-dev libxml2-dev libxslt1-dev python-pip python-virtualenv
