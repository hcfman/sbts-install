#!/bin/bash

abort() {
    echo $* >&2
    echo "Aborting..."
    exit 1
}

HERE=$(dirname $0)
cd "$HERE" || abort "Can't change to script directory"

export OPENBLAS_CORETYPE=ARMV8
while [ 1 ] ; do
    ./sbts-markup.py -b 127.0.0.1 -p 9999 ./sbts-annotate.py ./resources/config.json ../app/disk/sbts/images $*
    sleep 5
done

exit 0
