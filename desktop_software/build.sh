#!/bin/bash
rm dist/*.tar.gz
rm dist/*.whl
./check_code.sh
# Use poetry command to build python wheel
poetry -vvv build
rm linux/*.tar.gz 2>&1 > /dev/null
rm linux/*.whl 2>&1 > /dev/null
set -e
cp dist/*.tar.gz linux
cp dist/*.whl linux
rm -rf dist