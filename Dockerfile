FROM    otter/base

# The build process isn't a real tty
ENV     DEBIAN_FRONTEND noninteractive

# We want to use our own pypi repo
ENV     PIP_INDEX_URL http://pypi.as.rax.io/pypi/

RUN     pip install klein==0.2.1 twisted==13.1 tryfer==0.2.2 jsonschema==2.0 yunomi==0.2.2 iso8601==0.1.4 lxml==3.0.1 treq==0.2.0 silverberg==0.1.3 pyOpenSSL==0.13 jsonfig==0.1.1 testtools==0.9.32 croniter==0.3.3

ADD     . /opt/otter

CMD     cd /opt/otter; make run_docker
