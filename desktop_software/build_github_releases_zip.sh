#!/bin/bash
# This script generates the release zip file that can be added to github.

# Extract the package name from the pyproject.toml file
PACKAGE_NAME=$(grep -Po '(?<=^name = ")[^"]*' pyproject.toml)

# Extract the version from pyproject.toml
VERSION=$(grep -Po '(?<=^version = ")[^"]*' pyproject.toml)

# Define the directories to rename and the final zip filename
OUTPUT_DIR="$PACKAGE_NAME-github_release"
ZIP_FILE="$PACKAGE_NAME-$VERSION-release.zip"

# Create the output directory
mkdir -p "$OUTPUT_DIR"

# Copy the linux and windows folders
cp -rf linux "$OUTPUT_DIR/$PACKAGE_NAME_linux"
cp -rf windows "$OUTPUT_DIR/$PACKAGE_NAME_windows"

# Verify the rename operation
echo "Renamed directories:"
ls "$OUTPUT_DIR"

# Create the zip file containing the renamed folders
zip -r "$ZIP_FILE" "$OUTPUT_DIR"

# Clean up the temporary folder
rm -rf "$OUTPUT_DIR"

mv $ZIP_FILE github_releases/$ZIP_FILE
# Success message
echo "Release zip file created: github_releases/$ZIP_FILE"