#!/bin/bash
pyflakes3 src
pyflakes3 examples/project_template_1/main.py
pyflakes3 examples/project_template_2/app1/app.py

pyflakes3 examples/project_template_2/main.py
pyflakes3 examples/project_template_2/app1/app.py

pyflakes3 examples/project_template_3/main.py
pyflakes3 examples/project_template_3/app1/app.py


pycodestyle --max-line-length=250 src/*
pycodestyle --max-line-length=250 examples/project_template_1/*
pycodestyle --max-line-length=250 examples/project_template_2/*
pycodestyle --max-line-length=250 --exclude=*.md,*.cfg examples/project_template_3/*