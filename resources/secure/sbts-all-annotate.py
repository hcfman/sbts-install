#!/usr/bin/python3

# Copyright, 2024, Kim Hendrikse

import argparse
import asyncio
import json
import os
import sys
from os import listdir
from os.path import isfile, join

import re
import cv2
import numpy as np
import websockets


async def fetch(ws, image):
    try:
        await ws.send(image)
        r = await ws.recv()
        return json.loads(r)
    except websockets.ConnectionClosed as e:
        print("Caught error: {0}".format(e))
        print("Websocket closed exception, aborting: {0}, err: {1}".format(type(e).__name__, str(e)))
        os._exit(1)
    except Exception as e:
        print("Caught error: {0}".format(e))
        print("Exception, aborting: {0}, err: {1}".format(type(e).__name__, str(e)))
        os._exit(1)

def convertBack(x, y, w, h):
    xmin = int(round(x - (w / 2)))
    xmax = int(round(x + (w / 2)))
    ymin = int(round(y - (h / 2)))
    ymax = int(round(y + (h / 2)))
    return xmin, ymin, xmax, ymax

def drawTarget(image, category, prob, x, y, w, h):
    xmin, ymin, xmax, ymax = convertBack(float(x), float(y), float(w), float(h))
    pt1 = (xmin, ymin)
    pt2 = (xmax, ymax)
    cv2.rectangle(image, pt1, pt2, (0, 255, 0), 1)
    cv2.putText(image, "{0} {1:.2f}".format(category, prob), (pt1[0], pt1[1] + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, [0, 255, 0], 1)

def getFileList():
    fileList = []
    mypath = args.directory + os.path.sep
    for filename in sorted(listdir(args.directory)):
        fullPath = join(mypath, filename)
        if file_set is not None:
            if not filename in file_set:
                continue

        if isfile(fullPath) and filename.endswith(".jpg") and not "_ano_" in filename:
            fileList.append(fullPath)
    return fileList


def resize_image_if_needed(jpg, max_dimension):
    cv2_image = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)

    height, width = cv2_image.shape[:2]

    scaling_factor = max_dimension / float(max(height, width))

    # Check if the image exceeds the maximum dimensions and resize if necessary
    if scaling_factor < 1:
        new_dimensions = (int(width * scaling_factor), int(height * scaling_factor))
        resized_image = cv2.resize(cv2_image, new_dimensions, interpolation=cv2.INTER_AREA)

        success, encoded_image = cv2.imencode('.jpg', resized_image)
        if not success:
            raise Exception("Could not encode resized image to byte array")

        return encoded_image.tobytes()
    else:
        # Return the original image bytes if no resizing is needed
        return jpg

async def annotator():
    ws = await websockets.connect(args.url)
    for filename in getFileList():
        with open(filename, "rb") as infile:
            jpg = infile.read()

            if args.scale_to is not None:
                jpg = resize_image_if_needed(jpg, int(args.scale_to))

            new_image = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

            count_map = {}

            try:
                result = await fetch(ws, jpg)
                for item in result:
                    category = item[0]
                    prob = item[1]
                    x, y, w, h = item[2][0], item[2][1], item[2][2], item[2][3]
                    drawTarget(new_image, category, prob, int(x), int(y), int(w), int(h))

                    if args.c:
                        if category in count_map:
                            count_map[category] += 1
                        else:
                            count_map[category] = 1

                newImageName = filename.replace(".jpg", "_" + "ano.jpg")
                print("=> {}".format(newImageName))
                cv2.imwrite(newImageName, new_image)

                if args.c:
                    for name in sorted(count_map.keys()):
                        print(f"{name}: {count_map[name]}")

            except Exception as e:
                print("Caught exception: {0}", type(e))
                os._exit(1)

    os._exit(0)

def filter_images():
    files_set = set()

    if args.file_name_list is None:
        return

    if args.file_name_list == "-":
        for line in sys.stdin:
            files_set.add(line.strip())
    else:
        with open(args.file_name_list, 'r') as file:
            for line in file:
                files_set.add(line.strip())

    return files_set

async def main():
    await annotator()
    while True:
        await asyncio.sleep(3600)

directory = None

parser = argparse.ArgumentParser()
parser.add_argument("-f", "--file-name-list", dest="file_name_list", help="List of files from the directory to annotate")
parser.add_argument("-s", "--scale-to", dest="scale_to", help="Scale image size to this max for either width or height")
parser.add_argument('-c', action='store_true', help='Count all of the occurances of each match and output for each file')
parser.add_argument("directory", help="Directory")
parser.add_argument("url", help="Url of yolo server")
args = parser.parse_args()

if args.scale_to is not None and not re.match("^\d+$", args.scale_to):
    print("Scale to must be an integer")
    os._exit(1)

file_set = filter_images()

if __name__ == '__main__':
    # Check if asyncio.run is available (Python 3.7+)
    try:
        asyncio.run(main())
    except AttributeError:
        # Fallback for Python 3.6 and earlier
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(main())
        finally:
            loop.close()

os._exit(1)
