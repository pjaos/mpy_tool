#!/bin/bash
rm dist/*.tar.gz
rm dist/*.whl
./check_code.sh # Run some checks on the code before building it
cp pyproject.toml src/mpy_tool/assets
python3 copy_examples.py # Copy the examples folder to the assets folder so
                         # that the examples are available once installed.
# Use poetry command to build python wheel
poetry -vvv build
rm linux/*.tar.gz 2>&1 > /dev/null
rm linux/*.whl 2>&1 > /dev/null
#set -e
cp dist/*.tar.gz linux
cp dist/*.whl linux
rm -rf dist