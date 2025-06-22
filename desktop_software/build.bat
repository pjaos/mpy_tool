rmdir /s /q dist
rmdir /s /q windows
# Use poetry command to build python wheel
poetry -vvv build
move dist windows