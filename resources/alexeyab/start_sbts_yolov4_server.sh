#!/bin/bash

# Copyright (c) 2021 Kim Hendrikse

abort() {
    echo $* >&2
    echo "Aborting..."
    exit 1
}

HERE=$(dirname $0)
cd $HERE || abort "Can't change to script directory"

while [ 1 ] ; do
    ./sbts-yolov4-server.py
    sleep 5
done
