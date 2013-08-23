#!/bin/bash

CC_CONFIG=/root/.cloudcafe/configs/autoscale/preprod.config

sed -i "s/%user_password%/$CC_USER_PASSWORD/g" $CC_CONFIG
sed -i "s/%user_api_key%/$CC_USER_API_KEY/g" $CC_CONFIG
sed -i "s/%non_autoscale_user_password%/$CC_NON_AS_PASSWORD/g" $CC_CONFIG
sed -i "s/%otter_ip%/$OTTER_IP/g" $CC_CONFIG

cafe-runner autoscale preprod -p functional
