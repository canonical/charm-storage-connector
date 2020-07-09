#!/bin/bash

UPDATE=""
while getopts ":u" opt; do
  case $opt in
    u) UPDATE=true;;
  esac
done

git submodule update --init

# pbr seems unable to detect the current tag when installing
# from a local checkout using a git submodule. To work around this
# manually set the version.
export PBR_VERSION=$(cd mod/charm-helpers; git describe --tags)

if [[ -z "$UPDATE" ]]; then
    pip install -t lib -r build-requirements.txt
else
    git -C mod/operator pull origin master
    git -C mod/charm-helpers pull origin master
    pip install -t lib -r build-requirements.txt --upgrade
fi

ln -f -t lib -s ../mod/operator/ops