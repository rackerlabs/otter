FROM    otter/base

ADD     . /opt/otter
WORKDIR /opt/otter
RUN     pip install -r requirements.txt

CMD     ["make", "run_docker"]
