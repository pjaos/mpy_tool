#!/usr/bin/env python3

import os
import shutil

def ignore_file(directory, contents):
    # directory: the current folder being copied
    # contents: list of names in that folder
    return {name for name in contents if name in [".ropeproject"]}

if os.path.isdir('assets/examples/'):
    shutil.rmtree('assets/examples/')
os.mkdir('assets/examples/')
shutil.copytree(
    r"../mcu_template_software/examples/",
    r"assets/examples/",
    dirs_exist_ok=True,
    ignore=ignore_file,
    symlinks=False       # follow symlinks; copy actual files
)