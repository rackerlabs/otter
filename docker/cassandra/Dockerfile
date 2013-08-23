from java
ENV DEBIAN_FRONTEND noninteractive

run echo "deb http://archive.ubuntu.com/ubuntu precise universe" >> /etc/apt/sources.list
run apt-get update

# install Cassandra
RUN mkdir -p /var/lib/cassandra /var/lib/cassandra/saved_caches /var/lib/cassandra/commitlog /var/lib/cassandra/data /var/log/cassandra /opt
RUN cd /opt; wget https://e5bc0dd55ca88ce8c004-72925fc81183cc9670cdbad6a6b2643b.ssl.cf2.rackcdn.com/apache-cassandra-1.2.8-bin.tar.gz
RUN cd /opt; tar zxvf apache-cassandra-1.2.8-bin.tar.gz; mv apache-cassandra-1.2.8 cassandra

# setup libjna
RUN apt-get -y install libjna-java
RUN ln -sf /usr/share/java/jna.jar /opt/cassandra/lib

# Set the hostname so Cassandra doesn't explode
RUN echo "127.0.0.1 cassandra localhost" > /etc/hosts

ADD cassandra.yaml /opt/cassandra/conf/

# start Cassandra
EXPOSE 9160
EXPOSE 7199
CMD ["/opt/cassandra/bin/cassandra", "-f"]
