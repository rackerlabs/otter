from java
ENV DEBIAN_FRONTEND noninteractive

# install Repose
RUN mkdir -p /var/repose /var/log/repose /usr/share/lib/repose /usr/share/repose/filters
RUN wget --output-document=/usr/share/lib/repose/repose-valve.jar http://maven.research.rackspacecloud.com/content/repositories/releases/com/rackspace/papi/core/valve/2.8.2/valve-2.8.2.jar
RUN wget --output-document=/usr/share/repose/filters/filter-bundle.ear http://maven.research.rackspacecloud.com/content/repositories/releases/com/rackspace/papi/components/filter-bundle/2.8.2/filter-bundle-2.8.2.ear

# Set the hostname so Cassandra doesn't explode
RUN echo "127.0.0.1 repose localhost" > /etc/hosts

# expose repose and jmx
EXPOSE 8080
EXPOSE 9999

# repose configs
ADD ./configs /etc/repose

# set up start scripts
ADD ./start.sh /usr/bin/start_repose.sh
RUN chmod a+x /usr/bin/start_repose.sh

# start Repose
CMD ["start_repose.sh"]
