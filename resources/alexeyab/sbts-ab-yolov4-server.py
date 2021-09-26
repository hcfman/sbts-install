#!/usr/bin/python3

import sys
import asyncio
import json
import websockets
import argparse

import cv2
import numpy as np

from ctypes import *
import darknet

def detect_image(network, class_names, image, thresh=.5, hier_thresh=.5, nms=.45):
    pnum = pointer(c_int(0))
    darknet.predict_image(network, image)
    detections = darknet.get_network_boxes(network, image.w, image.h,
                                   thresh, hier_thresh, None, 0, pnum, 0)
    num = pnum[0]
    if nms:
        darknet.do_nms_sort(detections, num, len(class_names), nms)
    predictions = darknet.remove_negatives(detections, class_names, num)
    darknet.free_detections(detections, num)
    return sorted(predictions, key=lambda x: x[1])

def detect(network, class_names, image_bytes, thresh=.5):
    darknet_image = darknet.make_image(image_bytes.shape[1], image_bytes.shape[0], 3)

    image_rgb = cv2.cvtColor(image_bytes, cv2.COLOR_BGR2RGB)

    darknet.copy_image_from_bytes(darknet_image, image_rgb.tobytes())

    detections = detect_image(network, class_names, darknet_image, thresh=thresh)
    darknet.free_image(darknet_image)
    return detections

async def server_me(websocket, path):
    while True:
        try:
            blob_data = await websocket.recv()
        except websockets.ConnectionClosed:
            break

        new_rlist = []

        try:
            nparr = np.frombuffer(blob_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            r = detect(net, class_names, frame)

            r_list = [list(i) for i in r]
            for piece in r_list:
                new_rlist.append(tuple(piece))
        except Exception as e:
            new_rlist = []
            print("Caught exception converting image: {0}".format(type(e)))

        if debug:
            print("{0}".format(new_rlist))
            print()

        await websocket.send(json.dumps(new_rlist))

parser = argparse.ArgumentParser()
parser.add_argument("-b", "--bind", dest="bind_address", help="Bind address for the server")
parser.add_argument("-p", "--port", dest="server_port", help="Port for the server")
parser.add_argument("-d", "--debug", action="store_true", help="Enable debug output")
args = parser.parse_args()

if args.bind_address == None or args.server_port == None:
    print("You must supply both a server bind host address and port")
    sys.exit(1)

server_bind_address = args.bind_address
server_port = args.server_port
debug = args.debug

net, class_names, class_colors = darknet.load_network("cfg/sbts-yolov4.cfg", "cfg/coco.data", "yolov4.weights", batch_size=1)

start_server = websockets.serve(server_me, server_bind_address, server_port)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()

