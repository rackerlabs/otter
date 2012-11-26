#!/bin/bash
#
# Builds a "bundle" appropriate for deployment.
#
# terrarium builds a relocatable virtualenv, this script installs all the
# requirements from requirements.txt and otter into the virtualenv then
# creates a tarball for distribution and a sha checksum for verification.
#

set -e

NAME="otter-deploy"

TERRARIUM=$(which terrarium)
GIT_REV=$(git rev-parse HEAD)
SHA256="sha256sum"

LSB=""

if [[ $(which lsb_release) != "" ]]; then
    LSB="$(lsb_release -cs)-$(lsb_release -rs)-"
fi

if [[ "${BUILD_NUMBER}" != "" ]]; then
    BUILD_NUMBER="-${BUILD_NUMBER}"
fi

if [[ $(which ${SHA256}) == "" ]]; then
    SHA256="shasum -a 256"
fi

DIST="${NAME}-${LSB}${GIT_REV}${BUILD_NUMBER}.tar.gz"

# terrarium install's arguments are a list of requirements.txt formatted files
# This creates a ".self.txt" which contains only '.' indicating to install
# the current directory as if it were a requirement.

SELF_DEP="."

if [[ "$1" == "--dev" ]]; then
    SELF_DEP="-e .";
fi

echo "${SELF_DEP}" > ./.self.txt

echo "Building virtualenv..."
terrarium --target ${NAME} install ./requirements.txt ./.self.txt

echo "Generating distribution tarball..."
tar -zcvf ${DIST} ${NAME}

echo "Calculating checksum..."
${SHA256} ${DIST} | awk '{print $1}' > ${DIST}.sha256.txt
