#!/usr/bin/python3

import sys
import requests
import json

import argparse

import cv2
import numpy as np

from multi_secureparse.model import CameraReader

from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

drawn = False
area = []

def dumpJson(area):
    jsonArea = []
    for p in area:
        jsonArea.append({"x":p[0], "y": p[1]})
    print("{0}".format(json.dumps(jsonArea)))


def click_and_crop(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:

        if drawn:
            p = Point(x, y)
            if poly.contains(p):
                print("Inside")
            else:
                print("Outside")

        else:
            if area:
                cv2.line(frame, area[-1], (x, y), (0, 255, 255), 1)
                cv2.imshow("Image", frame)
            area.append((x, y))

def getSnapshot(reader, url):
    global args

    response = requests.get(url, auth=(reader.getUsername(), reader.getPassword()), stream=True)
    responseString = str(response)

    if responseString != '<Response [200]>':
        raise Exception("Bad response: {0}".format(responseString))

    stream_bytes = bytes()

    for chunk in response.iter_content(chunk_size=1024):
        stream_bytes += chunk
        a = stream_bytes.find(b'\xff\xd8')
        b = stream_bytes.find(b'\xff\xd9')
        if a != -1 and b != -1:
            jpg = stream_bytes[a:b + 2]
            frame = cv2.imdecode(np.fromstring(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

            if args.image is not None:
                cv2.imwrite(args.image, frame)
            return frame

def decorate(frame, reader):
    for notification in reader.getNotifyList():
        for zone in notification.getZoneList():
            for included in zone.getIncludeList():
                for modelList in included.getModels():
                    for model in modelList:
                        pts = np.array(model.getPolygon().getPointList(), np.int32)
                        cv2.polylines(frame, [pts], True, (0, 255, 255))
            for excluded in zone.getExcludeList():
                for modelList in excluded.getModels():
                    for model in modelList:
                        pts = np.array(model.getPolygon().getPointList(), np.int32)
                        cv2.polylines(frame, [pts], True, (0, 255, 255))

def initialize(configFilename, readerName):
    with open(configFilename) as infile:
        data = infile.read();
        configJson = json.loads(data)
        for camera in configJson["cameraList"]:
            reader = CameraReader.from_json(camera)
            if reader.getName() == readerName:
                return reader

    raise Exception("Reader {0} is not available".format(readerName))

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--image", dest="image", help="Path to image")
parser.add_argument("-s", "--snap", dest="url", help="URL to video stream")
parser.add_argument("cameraName", help="Name of camera")
parser.add_argument("configFile", help="Path to config file")
args = parser.parse_args()

if args.image is None and args.url is None:
    print("One of -i or -s must be entered")
    sys.exit(1)

reader = initialize(args.configFile, args.cameraName)

if args.image is not None and args.url is None:
    frame = cv2.imread(args.image)
else:
    frame = frame = getSnapshot(reader, args.url)

decorate(frame, reader)

cv2.namedWindow("Image")
cv2.setMouseCallback("Image", click_and_crop)

cv2.imshow("Image", frame)
while True:
    key = cv2.waitKey(0) & 0xFF

    if key == ord('d'):
        pts = np.array(area, np.int32)
        cv2.polylines(frame, [pts], True, (0, 255, 255))
        cv2.imshow("Image", frame)
        drawn = True
        poly = Polygon(area)

    if key == ord('q'):
        pts = np.array(area, np.int32)
        pts = pts.reshape((-1, 1, 2))
        cv2.polylines(frame, [pts], True, (0, 255, 255))
        dumpJson(area)
        break
