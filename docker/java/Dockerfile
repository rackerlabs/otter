from ubuntu:12.04
ENV DEBIAN_FRONTEND noninteractive

run apt-get -y install aptitude curl wget net-tools less

# install Java 6
run wget --no-cookies --no-check-certificate --header "Cookie: gpw_e24=http%3A%2F%2Fwww.oracle.com%2F" http://download.oracle.com/otn-pub/java/jdk/6u45-b06/jdk-6u45-linux-x64.bin
run chmod u+x jdk-6u45-linux-x64.bin
run ./jdk-6u45-linux-x64.bin
run mv jdk1.6.0_45 /opt
run update-alternatives --install "/usr/bin/java" "java" "/opt/jdk1.6.0_45/bin/java" 9999
