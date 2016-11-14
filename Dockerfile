FROM python:2.7
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN apt-get update && apt-get install -y jq

WORKDIR /otterapp 
COPY setup.py ./
COPY otter/ ./otter
COPY scripts/ ./scripts
COPY twisted/ ./twisted
RUN pip install .

# Customize config.json
COPY config.example.json ./
COPY otter_entrypoint.sh ./
ENTRYPOINT ["./otter_entrypoint.sh"]

EXPOSE 9000
ENV PYRSISTENT_NO_C_EXTENSION true
CMD ["twistd", "-n", "--logger=otter.log.observer_factory", "otter-api", "-c", "config.json"]
