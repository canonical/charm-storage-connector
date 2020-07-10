#!/bin/bash

git submodule update --init --recursive

git -C mod/operator pull origin master

ln -f -t lib -s ../mod/operator/ops