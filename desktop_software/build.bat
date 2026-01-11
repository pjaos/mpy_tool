copy /Y "pyproject.toml" "src/mpy_tool/assets"
rmdir /s /q dist
rmdir /s /q windows
python copy_examples.py # Copy the examples folder to the assets folder so
                         # that the examples are available once installed.
# Use poetry command to build python wheel
poetry -vvv build
move dist windows