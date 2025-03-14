# This is a template `Makefile` file for ops charms
# This file is managed by bootstack-charms-spec and should not be modified
# within individual charm repos. https://launchpad.net/bootstack-charms-spec

PYTHON := /usr/bin/python3

PROJECTPATH=$(dir $(realpath $(MAKEFILE_LIST)))
RELEASE_CHANNEL:=edge
METADATA_FILE="metadata.yaml"
CHARM_NAME=$(shell cat ${PROJECTPATH}/${METADATA_FILE} | grep -E '^name:' | awk '{print $$2}')

help:
	@echo "This project supports the following targets"
	@echo ""
	@echo " make help - show this text"
	@echo " make submodules - initialize, fetch, and checkout any nested submodules"
	@echo " make submodules-update - update submodules to latest changes on remote branch"
	@echo " make clean - remove unneeded files and clean charmcraft environment"
	@echo " make build - build the charm"
	@echo " make release - run clean, build and upload charm"
	@echo " make lint - run lint checkers"
	@echo " make reformat - run lint tools to auto format code"
	@echo " make unittests - run the tests defined in the unittest subdirectory"
	@echo " make functional - run the tests defined in the functional subdirectory"
	@echo " make test - run lint, unittests and functional targets"
	@echo ""

submodules:
	@echo "Cloning submodules"
	@git submodule update --init --recursive

submodules-update:
	@echo "Pulling latest updates for submodules"
	@git submodule update --init --recursive --remote --merge

clean:
	@echo "Cleaning existing build"
	@rm -rf ${PROJECTPATH}/${CHARM_NAME}*.charm
	@echo "Cleaning charmcraft"
	@charmcraft clean

build: clean
	@echo "Building charm"
	@charmcraft -v pack ${BUILD_ARGS}
	@bash -c ./rename.sh


release: build
	@echo "Releasing charm to ${RELEASE_CHANNEL} channel"
	@charmcraft upload ${CHARM_NAME}.charm --release ${RELEASE_CHANNEL}

lint:
	@echo "Running lint checks"
	@tox -e lint

reformat:
	@echo "Reformat files with black and isort"
	@tox -e reformat

unittests:
	@echo "Running unit tests"
	@tox -e unit -- ${UNIT_ARGS}

functional: build
	@echo "Executing functional tests using built charm at ${PROJECTPATH}"
	@CHARM_LOCATION=${PROJECTPATH} tox -e func -- ${FUNC_ARGS}

test: lint unittests functional
	@echo "Tests completed for charm ${CHARM_NAME}."

# The targets below don't depend on a file
.PHONY: help submodules submodules-update clean build lint reformat unittests functional
