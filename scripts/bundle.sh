#!/bin/bash
#
# Builds a "bundle" appropriate for deployment.
#
# terrarium builds a relocatable virtualenv, this script installs all the
# requirements from requirements.txt and otter into the virtualenv then
# creates a tarball for distribution and a sha checksum for verification.
#
# This only runs on Ubuntu.  It is intended to be used by chef (recipe[otter::dev])
# and Jenkins.
#

set -e

JOB_NAME=${JOB_NAME:="otter"}
NAME="${JOB_NAME}-deploy"
TARGET=${TARGET:="$NAME"}
DIST_DIR=${DIST_DIR:="."}

INSTALL_TARGET=${INSTALL_TARGET:="/opt/otter/current"}

TERRARIUM=$(which terrarium)
GIT_REV=$(git rev-parse HEAD)

LSB="$(lsb_release -cs)-$(lsb_release -rs)-"
BUILD_NUMBER="-${BUILD_NUMBER}"

if [[ "$1" == "--dev" ]]; then
    LSB="dev"
    GIT_REV=""
    BUILD_NUMBER=""
fi

DIST="${DIST_DIR}/${NAME}-${LSB}${GIT_REV}${BUILD_NUMBER}.tar.gz"

# terrarium install's arguments are a list of requirements.txt formatted files
# This creates a ".self.txt" which contains only '.' indicating to install
# the current directory as if it were a requirement.

SELF_DEP="$(pwd)"

if [[ "$1" == "--dev" ]]; then
    SELF_DEP="-e ${SELF_DEP}";
fi

echo "${SELF_DEP}" > ./.self.txt

REQUIREMENTS="./requirements.txt ./.self.txt"

if [[ "$1" == "--dev" ]]; then
    # if bundling for development, also include the development requirements
    echo "-e $(pwd)/autoscale_cloudcafe" >> ./.self.txt
    echo "-e $(pwd)/autoscale_cloudroast" >> ./.self.txt
    REQUIREMENTS="./dev_requirements.txt $REQUIREMENTS"
fi

echo "Building virtualenv..."
terrarium --no-bootstrap --target ${TARGET} install $REQUIREMENTS

echo "Virtualenv build.  Done."

if [[ "$1" == "--dev" ]]; then
    #
    # When using the -e argument in requirements.txt the files get installed
    # in 'editable' mode.
    #
    # This means the files are not copied into the virtualenv but their path
    # is written to an easy-install.pth file to be added to sys.path.
    #
    # The issue is that pip install -e (and therefore -e in requirements.txt)
    # writes a _relative_ path to the easy-install.pth file.
    #
    # This terrible piece of shell scripting rewrites all the relative paths
    # so you can still move the dev virtualenv outside of the otter repo
    # directory.
    #
    echo "Rewriting relative paths in easy-install.pth..."
    easy_install_pth=$(find ${TARGET} -name "easy-install.pth")
    site_packages=$(dirname ${easy_install_pth})
    egg_links=$(find ${site_packages} -name "*.egg-link")

    IFS=$(echo -e "\n\r")
    for link in ${egg_links}; do
        link_val=$(cat ${link})
        real_path=$(cd ${site_packages}; cd ${link_val}; pwd);
        echo "Changing ${link_val} to ${real_path}"
        sed -ie "s|^${link_val}\$|${real_path}\n|g" ${easy_install_pth}
    done

    unset IFS
fi

echo "Rewrite virtualenv PATH..."
sed -i \
    -e "s|VIRTUAL_ENV=\".*\"|VIRTUAL_ENV=\"${INSTALL_TARGET}\"|" \
    "${TARGET}/bin/activate";

echo "Generating distribution tarball..."
tar -zcvf ${DIST} -C ${TARGET} \
    --dereference \
    --hard-dereference \
    --exclude 'local' \
    --exclude-vcs .;

echo "Calculating checksum..."
sha256sum ${DIST} | awk '{print $1}' > ${DIST}.sha256.txt
