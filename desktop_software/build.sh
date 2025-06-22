#!/bin/bash
set -e
rm -rf dist
rm -rf linux
./check_code.sh
# Use poetry command to build python wheel
poetry -vvv build
mv dist linux
