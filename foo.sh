#!/bin/bash

X='boids'
if [ "$X" = "boids" ] 
then
    echo "Directory /path/to/dir exists." 
else
    echo "Error: Directory /path/to/dir does not exists."
fi
