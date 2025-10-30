#!/bin/bash

# Remove existing python env
# Uncomment this if you want to rebuild the python env from scratch
#poetry env remove python3

python3 -m poetry lock
python3 -m poetry install
