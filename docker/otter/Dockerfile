FROM python:2.7
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Use dockerize to wait for services to come up when bootstraping
RUN apt-get update && apt-get install -y wget
ENV DOCKERIZE_VERSION v0.2.0
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz

WORKDIR /app
COPY setup.py ./
COPY otter/ ./otter
COPY scripts/ ./scripts
COPY twisted/ ./twisted
COPY schema/ ./schema
RUN pip install -e .

# Customize config.json
WORKDIR /
COPY config.example.json /
COPY docker/otter/docker_entrypoint.sh /
ENTRYPOINT ["/docker_entrypoint.sh"]

EXPOSE 9000
ENV PYRSISTENT_NO_C_EXTENSION true
CMD ["twistd", "-n", "--logger=otter.log.observer_factory", "otter-api", "-c", "/etc/otter.json"]
