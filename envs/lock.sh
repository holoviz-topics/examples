#!/bin/bash

# Command to run after environment.yml is updated.

# Relocking the environment for all the platforms.
conda-lock lock --file environment.yml --filename-template environment-{platform}.lock --kind explicit -p osx-64 -p win-64 -p linux-64 -p osx-arm64

# Updating the filenames as these lock files are used on the CI, depending on the Github runner selected.
# I.e. ubuntu-latest is a Github runner, not linux-64.
mv environment-linux-64.lock environment-ubuntu-latest.lock
mv environment-osx-64.lock environment-macos-latest.lock
mv environment-win-64.lock environment-windows-latest.lock
