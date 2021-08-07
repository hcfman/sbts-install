#!/usr/bin/python3

import asyncio
import json
import websockets

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
    blob_data = await websocket.recv()

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
    print("{0}".format(new_rlist))
    print()

    await websocket.send(json.dumps(new_rlist))


if __name__ == "__main__":
    net, class_names, class_colors = darknet.load_network("cfg/sbts-yolov3.cfg", "cfg/coco.data", "yolov3.weights", batch_size=1)

    start_server = websockets.serve(server_me, "0.0.0.0", 8765)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()

