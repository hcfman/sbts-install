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
    ./sbts-scaled-yolov4-large-server.py -b 0.0.0.0 -p 8767 --device 0 --img-size 1536 --weights weights/yolov4-p7.pt
    sleep 5
done
