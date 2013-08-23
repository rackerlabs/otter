from ubuntu:12.04
ENV DEBIAN_FRONTEND noninteractive

run apt-get -y install aptitude curl wget net-tools less

# install Java 6
run wget --no-cookies --no-check-certificate --header "Cookie: gpw_e24=http%3A%2F%2Fwww.oracle.com%2F" http://download.oracle.com/otn-pub/java/jdk/6u45-b06/jdk-6u45-linux-x64.bin
run chmod u+x jdk-6u45-linux-x64.bin
run ./jdk-6u45-linux-x64.bin
run mv jdk1.6.0_45 /opt
run update-alternatives --install "/usr/bin/java" "java" "/opt/jdk1.6.0_45/bin/java" 9999

# add Ubuntu and Datastax repositories
run echo "deb http://archive.ubuntu.com/ubuntu precise universe" >> /etc/apt/sources.list
run apt-get update

# install Cassandra
RUN mkdir -p /var/lib/cassandra /var/lib/cassandra/saved_caches /var/lib/cassandra/commitlog /var/lib/cassandra/data /var/log/cassandra /opt
RUN cd /opt; wget https://e5bc0dd55ca88ce8c004-72925fc81183cc9670cdbad6a6b2643b.ssl.cf2.rackcdn.com/apache-cassandra-1.2.8-bin.tar.gz
RUN cd /opt; tar zxvf apache-cassandra-1.2.8-bin.tar.gz; ln -sf /opt/apache-cassandra-1.2.8/ cassandra

# setup libjna
RUN apt-get -y install libjna-java
RUN ln -sf /usr/share/java/jna.jar /opt/cassandra/lib

# Set the hostname so Cassandra doesn't explode
RUN echo "127.0.0.1 cassandra localhost" > /etc/hosts

# TODO: Add cassandra.yaml with settings close to our prod settings

# start Cassandra
EXPOSE 9160
EXPOSE 7199
CMD ["/opt/cassandra/bin/cassandra", "-f"]
