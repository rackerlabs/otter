FROM    otter/base

# The build process isn't a real tty
ENV     DEBIAN_FRONTEND noninteractive
ENV     JENKINS_URL http://placeholder
ENV     HOME /root

# HOLY CRAP
ENV     SUDO_USER root

# We want to use our own pypi repo
ENV     PIP_INDEX_URL http://pypi.as.rax.io/pypi/

RUN     pip install pep257==0.2.0 pep8==1.3.3 pyflakes==0.5.0 mock==1.0.1 coverage==3.5.3 python-subunit==0.0.8 junitxml==0.7 paramiko==1.10.0 requests==1.2.0 decorator==3.4.0 unittest2==0.5.1 git+https://github.com/stackforge/opencafe.git@b971070b28d07c0b19f8809e18950f2d6cf0e466#egg=opencafe git+https://github.com/stackforge/cloudcafe.git@4dc2227b4b0140158ceab286dfa127384886f5b7#egg=cloudcafe IPy==0.81

RUN     mkdir -p /root/.cloudcafe/configs/autoscale

ADD     preprod.config /root/.cloudcafe/configs/autoscale/
ADD     run_cloudcafe.sh /srv/run_cloudcafe.sh
RUN     /bin/chmod +x /srv/run_cloudcafe.sh

ADD     autoscale_cloudcafe /opt/autoscale_cloudcafe
ADD     autoscale_cloudroast /opt/autoscale_cloudroast
RUN     cd /opt/autoscale_cloudcafe && python setup.py install
RUN     cd /opt/autoscale_cloudroast && python setup.py install

CMD     ["/srv/run_cloudcafe.sh"]
