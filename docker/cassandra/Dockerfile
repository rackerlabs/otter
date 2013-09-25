FROM java

# install Cassandra
RUN mkdir -p /var/lib/cassandra /var/lib/cassandra/saved_caches /var/lib/cassandra/commitlog /var/lib/cassandra/data /var/log/cassandra /opt
ADD https://e5bc0dd55ca88ce8c004-72925fc81183cc9670cdbad6a6b2643b.ssl.cf2.rackcdn.com/apache-cassandra-1.2.8-bin.tar.gz /opt/
RUN cd /opt; tar zxf apache-cassandra-1.2.8-bin.tar.gz; mv apache-cassandra-1.2.8 cassandra

# setup libjna
RUN echo "deb http://us.archive.ubuntu.com/ubuntu precise universe" >> /etc/apt/sources.list
RUN apt-get update
RUN apt-get -y -q install libjna-java
RUN ln -sf /usr/share/java/jna.jar /opt/cassandra/lib

# Set the hostname so Cassandra doesn't explode
RUN echo "127.0.0.1 cassandra localhost" > /etc/hosts

ADD cassandra.yaml /opt/cassandra/conf/

# start Cassandra
EXPOSE 9160
EXPOSE 7199
CMD /opt/cassandra/bin/cassandra -f
