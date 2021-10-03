#!/bin/bash

# Copyright, 2021, Kim Hendrikse

abort() {
    echo $* >&2
    echo "Aborting..."
    exit 1
}

HERE=$(dirname $0)
cd "$HERE" || abort "Can't change to script directory"

while [ 1 ] ; do
    ./sbts-secure.py -b 127.0.0.1 -p 8764 resources/config.json
    sleep 1
done

exit 0
