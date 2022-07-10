#!/data1/home/kim/virtualenvs/pytorch/bin/python3

import argparse
import asyncio
import cv2
import json
import sys

import numpy as np
import torch
import websockets

from models.experimental import attempt_load
from utils.general import (
    check_img_size, non_max_suppression, scale_coords, xyxy2xywh)
from utils.torch_utils import select_device, time_synchronized


def letterbox(img, new_shape=(640, 640), color=(114, 114, 114), auto=True, scaleFill=False, scaleup=True):
    # Resize image to a 32-pixel-multiple rectangle https://github.com/ultralytics/yolov3/issues/232
    shape = img.shape[:2]  # current shape [height, width]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    # Scale ratio (new / old)
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    if not scaleup:  # only scale down, do not scale up (for better test mAP)
        r = min(r, 1.0)

    # Compute padding
    ratio = r, r  # width, height ratios
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding
    if auto:  # minimum rectangle
        dw, dh = np.mod(dw, 128), np.mod(dh, 128)  # wh padding
    elif scaleFill:  # stretch
        dw, dh = 0.0, 0.0
        new_unpad = (new_shape[1], new_shape[0])
        ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]  # width, height ratios

    dw /= 2  # divide padding into 2 sides
    dh /= 2

    if shape[::-1] != new_unpad:  # resize
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)  # add border
    return img, ratio, (dw, dh)

async def server_me(websocket, path):
    global source, weights, view_img, save_txt, imgsz, names, device, half, model

    while True:
        try:
            blob_data = await websocket.recv()
        except websockets.ConnectionClosed:
            break

        new_rlist = []

        try:
            nparr = np.frombuffer(blob_data, np.uint8)
            im0 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # Copied from utils/datasets LoadImages
            img = letterbox(im0, new_shape=640)[0]

            # Convert
            img = img[:, :, ::-1].transpose(2, 0, 1)  # BGR to RGB, to 3x416x416
            img = np.ascontiguousarray(img)

            img = torch.from_numpy(img).to(device)
            img = img.half() if half else img.float()  # uint8 to fp16/32
            img /= 255.0  # 0 - 255 to 0.0 - 1.0
            if img.ndimension() == 3:
                img = img.unsqueeze(0)

            # Inference
            oldTime = time_synchronized()
            pred = model(img, augment=opt.augment)[0]

            # Apply NMS
            pred = non_max_suppression(pred, opt.conf_thres, opt.iou_thres, classes=opt.classes,
                                       agnostic=opt.agnostic_nms)
            newTime = time_synchronized()

            for i, det in enumerate(pred):
                if det is not None and len(det):
                    # Rescale boxes from img_size to im0 size
                    det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()
                    for *xyxy, conf, cls in det:
                        xywh = (xyxy2xywh(torch.tensor(xyxy).view(1, 4))).view(-1).tolist()  # normalized xywh
                        newPiece = [names[int(cls)], conf.item() , xywh]
                        new_rlist.append(tuple(newPiece))

        except Exception as e:
            new_rlist = []
            print("Caught exception converting image: {0} {1}".format(type(e).__name__, str(e)))

        if debug:
            print("{0}".format(new_rlist))
            print()

        if debug:
            print(">>> Last result in {0:.3f}".format(newTime - oldTime))
        await websocket.send(json.dumps(new_rlist))


def initialize():
    global source, weights, view_img, save_txt, imgsz, names, device, half, model

    source, weights, view_img, save_txt, imgsz = \
        opt.source, opt.weights, opt.view_img, opt.save_txt, opt.img_size

    # Initialize
    device = select_device(opt.device)
    half = device.type != 'cpu'  # half precision only supported on CUDA

    # Load model
    model = attempt_load(weights, map_location=device)  # load FP32 model
    imgsz = check_img_size(imgsz, s=model.stride.max())  # check img_size
    if half:
        model.half()  # to FP16

    # Get names
    names = model.module.names if hasattr(model, 'module') else model.names

    # Run inference
    img = torch.zeros((1, 3, imgsz, imgsz), device=device)  # init img
    _ = model(img.half() if half else img) if device.type != 'cpu' else None  # run once

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', nargs='+', type=str, default='yolor-p6.pt', help='model.pt path(s)')
    parser.add_argument('--source', type=str, default='inference/images', help='source')  # file/folder, 0 for webcam
    parser.add_argument('--output', type=str, default='inference/output', help='output folder')  # output folder
    parser.add_argument('--img-size', type=int, default=1280, help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.25, help='object confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.45, help='IOU threshold for NMS')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', action='store_true', help='display results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--update', action='store_true', help='update all models')

    parser.add_argument("-b", "--bind", dest="bind_address", help="Bind address for the server")
    parser.add_argument("-p", "--port", dest="server_port", help="Port for the server")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug output")

    opt = parser.parse_args()

    if opt.bind_address == None or opt.server_port == None:
        print("You must supply both a server bind host address and port")
        sys.exit(1)

    server_bind_address = opt.bind_address
    server_port = opt.server_port
    debug = opt.debug

    print(opt)

    with torch.no_grad():
        initialize()
        start_server = websockets.serve(server_me, server_bind_address, server_port)

        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()
