FROM python:2.7
COPY cafe_requirements.txt /tmp/
# Below env due to https://github.com/openstack/opencafe/blob/b971070b28d07c0b19f8809e18950f2d6cf0e466/setup.py#L127
ENV SUDO_USER root
RUN pip install --no-cache-dir -r /tmp/cafe_requirements.txt

WORKDIR /cafe
COPY autoscale_cloudcafe/ ./autoscale_cloudcafe
COPY autoscale_cloudroast/ ./autoscale_cloudroast
RUN pip install -e autoscale_cloudcafe/ -e autoscale_cloudroast/

# Use dockerize to wait for otter to come up
RUN apt-get update && apt-get install -y wget
ENV DOCKERIZE_VERSION v0.2.0
RUN wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz

COPY docker/cafe/dev-convergence.config /root/.cloudcafe/configs/autoscale/dev-convergence.config
COPY docker/cafe/dev-worker.config /root/.cloudcafe/configs/autoscale/dev-worker.config

COPY docker/cafe/docker_entrypoint.sh /

ENTRYPOINT ["/docker_entrypoint.sh"]
CMD ["dev-convergence", "-l", "tests"]
