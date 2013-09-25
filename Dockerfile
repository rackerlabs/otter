FROM    otter/base

# CloudCafe requires a SUDO_USER environment variable
ENV     SUDO_USER root
ENV     HOME /root

ADD     . /opt/otter
WORKDIR /opt/otter
RUN     pip install -r dev_requirements.txt
RUN     pip install -r requirements.txt

CMD     ["make", "run_docker"]
