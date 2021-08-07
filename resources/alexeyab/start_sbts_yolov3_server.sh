#!/bin/bash

abort() {
    echo $* >&2
    echo "Aborting..."
    exit 1
}

HERE=$(dirname $0)
cd $HERE || abort "Can't change to script directory"

while [ 1 ] ; do
    ./sbts-yolov3-server.py
    sleep 5
done
