#!/bin/sh

while [ 1 ] ; do
    cvlc  -v rtsp://myusername:mypassword@192.168.1.65/PSI/streaming/channels/102 --http-reconnect \
	--sout-keep --sout '#duplicate{dst=std{access=http{mime=multipart/x-mixed-replace;boundary=--7b3cc56e5f51db803f790dad720ed50a,user=santa,pwd=youtube},mux=mpjpeg,dst=:8101/back/video.jpg}}' vlc://quit
    sleep 10
done
