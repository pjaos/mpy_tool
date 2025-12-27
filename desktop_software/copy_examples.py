#!/usr/bin/env python3

import shutil

def ignore_ropeproject(directory, contents):
    # directory: the current folder being copied
    # contents: list of names in that folder
    return {name for name in contents if name == ".ropeproject"}

shutil.rmtree('assets/examples/')
shutil.copytree(
    r"../mcu_template_software/examples/",
    r"assets/examples/",
    dirs_exist_ok=True,
    ignore=ignore_ropeproject,
    symlinks=False       # follow symlinks; copy actual files
)