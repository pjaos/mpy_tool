#!/bin/bash
set -e
pyflakes3 src/mpy_tool/*.py
pyflakes3 src/lib/*.py

