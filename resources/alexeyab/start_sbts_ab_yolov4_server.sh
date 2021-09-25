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
    ./sbts-ab-yolov4-server.py -b 127.0.0.1 -p 8766
    sleep 5
done
