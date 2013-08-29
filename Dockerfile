FROM    otter/base

ADD     . /opt/otter
RUN     pip install -r requirements.txt

WORKDIR /opt/otter
CMD     ["make", "run_docker"]
