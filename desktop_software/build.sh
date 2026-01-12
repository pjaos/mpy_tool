#!/bin/bash
./check_code.sh # Run some checks on the code before building it
cp pyproject.toml src/mpy_tool/assets
python3 copy_examples.py # Copy the examples folder to the assets folder so
                         # that the examples are available once installed.
# Use poetry command to build python wheel
poetry --output=linux --clean -vvv build
# Delete the .tar.gz file in dist directory
rm -f linux/*.tar.gz
# Put a copy of the install.py alongside the python wheel
cp install.py linux