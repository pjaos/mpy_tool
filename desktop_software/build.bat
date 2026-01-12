copy /Y "pyproject.toml" "src/mpy_tool/assets"
:: Copy the examples folder to the assets folder so that the examples are available once installed.
python copy_examples.py 
:: Use poetry command to build python wheel
poetry --output=windows --clean -vvv build 
:: We want windows in the filename so that both the linux/macos wheels and the windows wheels can be added to github releases
:: Delete the .tar.gz file in windows directory (if it exists)
del "windows\*.tar.gz"
:: Put a copy of the install.py alongside the python wheel
copy .\install.py .\windows\