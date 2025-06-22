#!/bin/bash

# Remove and reinstall poetry
#curl -sSL https://install.python-poetry.org | python3 - --uninstall
#curl -sSL https://install.python-poetry.org | python3 -
#poetry self add poetry-plugin-shell

# Remove existing python env
# Uncomment this if you want to rebuild the python env from scratch
poetry env remove python3

poetry self add poetry-plugin-shell
poetry lock 
poetry install --no-root
