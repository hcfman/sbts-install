#!/bin/bash

# Copyright (c) 2022 Kim Hendrikse

abort() {
    echo $* >&2
    echo "Aborting..."
    exit 1
}

HERE=$(dirname $0)
cd $HERE || abort "Can't change to script directory"

export OPENBLAS_CORETYPE=ARMV8

while [ 1 ] ; do
    ./sbts-ab-yolov4-server.py -b 127.0.0.1 -p 8766
    sleep 5
done
