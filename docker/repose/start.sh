#!/bin/bash

[ -z "${IDENTITY_URL}" ] && IDENTITY_URL="https://identity.api.rackspacecloud.com/v2.0"

[ -z "${AUTOSCALE_URL}" ] && AUTOSCALE_URL=`echo https://${AUTOSCALE_REGION}.autoscale.api.rackspacecloud.com/v1.0 | tr '[A-Z]' '[a-z]'`

[ -z "${OTTER_PORT}" ] && OTTER_PORT="9160"


UPPERCASE_REGION=`echo ${AUTOSCALE_REGION} | tr '[a-z]' '[A-Z]'`

echo "${IDENTITY_URL}"

find /etc/repose -type f -exec sed -i "s|%identity_username%|${IDENTITY_USERNAME}|g" {} \;
find /etc/repose -type f -exec sed -i "s|%identity_password%|${IDENTITY_PASSWORD}|g" {} \;
find /etc/repose -type f -exec sed -i "s|%identity_url%|${IDENTITY_URL}|g" {} \;

find /etc/repose -type f -exec sed -i "s|%autoscale_url%|${AUTOSCALE_URL}|g" {} \;
find /etc/repose -type f -exec sed -i "s|%autoscale_region%|${UPPERCASE_REGION}|g" {} \;


sed -i "s/%otter_host%/${OTTER_IP}/g" /etc/repose/system-model.cfg.xml
sed -i "s/%otter_port%/${OTTER_PORT}/g" /etc/repose/system-model.cfg.xml

/usr/bin/java \
    -Dcom.sun.management.jmxremote.port=9999 \
    -Dcom.sun.management.jmxremote.authenticate=false \
    -Dcom.sun.management.jmxremote.ssl=false \
    -jar /usr/share/lib/repose/repose-valve.jar START -s 8123 -c /etc/repose
