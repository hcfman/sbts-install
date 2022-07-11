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
    ./sbts-yolov7-server.py -b 0.0.0.0 -p 8769 -d --device 0 --img-size 640 --weights weights/yolov7-e6e.pt
    sleep 5
done
