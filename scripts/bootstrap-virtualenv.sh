#!/bin/bash
#
# Create an initial virtualenv based on the VE_DIR environment variable (.ve)
# by default.  This is used by the Makefile `make env` to allow bootstrapping in
# environments where virtualenvwrapper is unavailable or unappropriate.  Such
# as on Jenkins.
#

VE_DIR=${VE_DIR:=.ve}

if [[ -d ${VE_DIR} ]]; then
    echo "Skipping build virtualenv"
else
    echo "Building complete virtualenv"
    virtualenv ${VE_DIR}
fi

source ${VE_DIR}/bin/activate

pip install -r opt_requirements.txt
pip install -r dev_requirements.txt
pip install -r requirements.txt
