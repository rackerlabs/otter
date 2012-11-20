#!/bin/bash
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

if [[ $(which sha256sum) == "" ]]; then
    SHA256="shasum -a 256"
fi

DIST="${NAME}-${LSB}${GIT_REV}${BUILD_NUMBER}.tar.gz"

echo "." > ./.self.txt

echo "Building virtualenv..."
terrarium --target ${NAME} install ./requirements.txt ./.self.txt

echo "Generating distribution tarball..."
tar -zcvf ${DIST} ${NAME}

echo "Calculating checksum..."
${SHA256} ${DIST} | awk '{print $1}' > ${DIST}.sha256.txt
