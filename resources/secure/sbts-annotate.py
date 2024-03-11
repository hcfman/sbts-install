#!/usr/bin/python3

# Copyright, 2021, Kim Hendrikse

import argparse
import asyncio
import json
import os
import re
import sys
from os import listdir
from os.path import isfile, join

import cv2
import numpy as np
import websockets

from multi_secureparse.model import SecureConfig, CameraReader, ModelMap

class FrameMap():
    def __init__(self, image):
        self.theMap = {}
        self.image = image

    def getFrame(self, modelName):
        if not modelName in self.theMap:
            self.theMap[modelName] = cv2.imdecode(np.fromstring(self.image, dtype=np.uint8), cv2.IMREAD_COLOR)

        return self.theMap[modelName]

    def getFrameMap(self):
        return self.theMap

class ResultCache():
    def __init__(self, wsMap):
        self.wsMap = wsMap
        self.cachedResult = {}
        self.categoryMap = {}
        self.advanceSkip = False
        self.fired = False

    async def fetch(self, ws, modelName, image):
        try:
            await ws.send(image)
            r = await ws.recv()
            resultJson = json.loads(r)
            self.cachedResult[modelName] = resultJson

            # Construct map by category of matches
            if not modelName in self.categoryMap.keys():
                self.categoryMap[modelName] = {}

            for el in resultJson:
                if el[0] not in self.categoryMap[modelName].keys():
                    self.categoryMap[modelName][el[0]] = []
                self.categoryMap[modelName][el[0]].append(el)

            return resultJson
        except websockets.ConnectionClosed as e:
            print("Websocket closed exception, aborting: {0}, err: {1}".format(type(e).__name__, str(e)))
            os._exit(1)

    async def getResult(self, modelName, image):
        ws = self.wsMap[modelName]
        if modelName in self.cachedResult.keys():
            return self.cachedResult[modelName]
        else:
            return await self.fetch(ws, modelName, image)

    async def getResult(self, modelName, category, image):
        ws = self.wsMap[modelName]
        if not modelName in self.categoryMap.keys():
            await self.fetch(ws, modelName, image)

        if category in self.categoryMap[modelName].keys():
            return self.categoryMap[modelName][category]
        else:
            return []

    def getWsList(self):
        return self.wsMap

    def getAdvanceSkip(self):
        return self.advanceSkip

    def getFired(self):
        return self.fired

def convertBack(x, y, w, h):
    xmin = int(round(x - (w / 2)))
    xmax = int(round(x + (w / 2)))
    ymin = int(round(y - (h / 2)))
    ymax = int(round(y + (h / 2)))
    return xmin, ymin, xmax, ymax

def drawTargetCross(x, y, frame, included:bool):
    if included:
        cv2.putText(frame, "x", (int(x), int(y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, [255, 0, 0], 2)
    else:
        cv2.putText(frame, "x", (int(x), int(y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, [0, 0, 255], 2)

def drawTarget(model, prob, x, y, w, h, frameMap):
    xmin, ymin, xmax, ymax = convertBack(float(x), float(y), float(w), float(h))
    pt1 = (xmin, ymin)
    pt2 = (xmax, ymax)
    cv2.rectangle(frameMap.getFrame(model.getName()), pt1, pt2, (0, 255, 0), 1)
    cv2.putText(frameMap.getFrame(model.getName()), "{0} {1:.2f}".format(model.getCategory(), prob), (pt1[0], pt1[1] + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, [0, 255, 0], 1)

async def processResult(frameMap, resultCache, image, camera:CameraReader):
    for notify in camera.getNotifyList():
        if len(notify_set) > 0 and notify.getName() not in notify_set:
            continue
        else:
            for zone in notify.getZoneList():
                for include in zone.getIncludeList():
                    await checkIncluded(frameMap, image, include, resultCache, True)

                for include in zone.getExcludeList():
                    await checkIncluded(frameMap, image, include, resultCache, False)

async def checkIncluded(frameMap, image, include, resultCache, included:bool):
    global neverDrawn
    global model_prob_map

    if included:
        model_prob_map = {}

    for modelList in include.getModels():
        triggerCount = 0
        for model in modelList:
            result = await resultCache.getResult(model.getName(), model.getCategory(), image)

            count = 0
            for item in result:
                neverDrawn = False
                prob = item[1]
                x, y, w, h = item[2][0], item[2][1], item[2][2], item[2][3]
                drawTarget(model, prob, int(x), int(y), int(w), int(h), frameMap)
                if (model.isContained(prob, int(x), int(y), int(w), int(h))):
                    count += 1

                    if count > 0:
                        drawTargetCross(int(x), int(y), frameMap.getFrame(model.getName()), included)
                        triggerCount += 1

                        if included:
                            model_prob_map[model.getName()] = prob

def readConfigFile():
    global parser

    with open(args.configFile) as infile:
        data = infile.read();
        configJson = json.loads(data)

        if not args.model_list is None:
            regexp = re.compile("^(.*?):(.*)$")
            modelsMap = {}
            for mapping in args.model_list.split(','):
                m = regexp.match(mapping)
                name = m.group(1)
                url = m.group(2)
                modelsMap[name] = {}
                modelsMap[name]['url'] = url
        else:
            modelsMap = ModelMap.from_json(configJson["modelList"]).getModelsMap()
        cameras = []
        for camera in configJson["cameraList"]:
            if camera["name"] == args.cameraName:
                cameraReader = CameraReader.from_json(camera)
                cameraReader.enable()
                cameras.append(cameraReader)

        return SecureConfig(modelsMap, cameras)

def drawRegions(frameMap, camera):
    global neverDrawn

    for notify in camera.getNotifyList():
        for zone in notify.getZoneList():
            if len(notify_set) > 0 and notify.getName() not in notify_set:
                continue
            for include in zone.getIncludeList():
                for modelList in include.getModels():
                    for model in modelList:
                        pts = np.array(model.getPolygon().getPointList(), np.int32)
                        cv2.polylines(frameMap.getFrame(model.getName()), [pts], True, (0, 255, 255))

            if len(notify_set) == 0:
                for exclude in zone.getExcludeList():
                    for modelList in exclude.getModels():
                        for model in modelList:
                            pts = np.array(model.getPolygon().getPointList(), np.int32)
                            cv2.polylines(frameMap.getFrame(model.getName()), [pts], True, (0, 0, 255))

def getFileList():
    global start_range, end_range

    pattern = re.compile(r'^(\d{4})\.jpg$')

    fileList = []
    mypath = args.directory + os.path.sep
    for filename in sorted(listdir(args.directory)):
        fullPath = join(mypath, filename)
        if file_set is not None:
            if not filename in file_set:
                continue

        match = pattern.match(filename)
        if match:
            file_number = int(match.group(1))
            if file_number < start_range or file_number > end_range:
                continue

        if isfile(fullPath) and filename.endswith(".jpg") and not "_ano_" in filename:
            fileList.append(fullPath)
    return fileList

def initWebsocketMap(secureConfig):
    wsMap = {}
    for modelName in secureConfig.getModelsMap().keys():
        modelsMap = secureConfig.getModelsMap()
        modelMapJson = modelsMap[modelName]
        url = modelMapJson['url']
        ws = yield from websockets.connect(url)
        wsMap[modelName] = ws
    return wsMap

def highest_prob(model_prob_map):
    # Check if the dictionary is empty
    if not model_prob_map:
        return None
    else:
        # Find the key with the highest value
        return max(model_prob_map, key=model_prob_map.get)

@asyncio.coroutine
def annotator():
    # Read the configuration json file
    secureConfig = readConfigFile()

    camera = None
    for cam in secureConfig.getCameras():
        if cam.getName() == args.cameraName:
            camera = cam
            break

    if camera is None:
        print("Can't find camera \"\" in the configuration file".format(args.cameraName))
        sys.exit(1)

    # Create websocket connections for the models
    wsMap = yield from initWebsocketMap(secureConfig)

    for filename in getFileList():
        print("{0}".format(filename))
        with open(filename, "rb") as infile:
            jpg = infile.read()

            try:
                frameMap = FrameMap(jpg)
                resultCache = ResultCache(wsMap)
                drawRegions(frameMap, camera)

                yield from processResult(frameMap, resultCache, jpg, camera)

                chosen_model = highest_prob(model_prob_map)
                for item in frameMap.getFrameMap().items():
                    if args.notifications is not None:
                        if chosen_model is not None and item[0] == chosen_model:
                            temp_filename = os.path.join(os.path.dirname(filename), '.' + os.path.basename(filename))
                            print("=> {}".format(filename))
                            cv2.imwrite(temp_filename, item[1])
                            os.remove(filename)
                            os.rename(temp_filename, filename)
                    else:
                        newImageName = filename.replace(".jpg", "_" + "ano_" + item[0] + ".jpg")
                        print("=> {}".format(newImageName))
                        cv2.imwrite(newImageName, item[1])

            except Exception as e:
                print("Caught exception: {0}", type(e))
                os._exit(1)

    sys.exit(0)

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

def define_relevant_notifications():
    if args.notifications is None:
        return set()

    return set(args.notifications.split(','))

def check_numbers():
    global start_range, end_range

    if args.num_range is None:
        return

    pattern = re.compile(r'^(\d{1,4}),(\d{1,4})$')
    match = pattern.match(args.num_range)
    if match:
        start_range = int(match.group(1))
        end_range = int(match.group(2))

def initialize(configFilename, readers):
    with open(configFilename) as infile:
        data = infile.read();
        configJson = json.loads(data)
        for camera in configJson["cameraList"]:
            readers.append(CameraReader.from_json(camera))

directory = None

parser = argparse.ArgumentParser()
parser.add_argument("-m", "--model-list", dest="model_list", help="List of models and their websocket urls")
parser.add_argument("-f", "--file-name-list", dest="file_name_list", help="List of files from the directory to annotate")
parser.add_argument("-n", "--notifications", dest="notifications", help="Relevant notifications")
parser.add_argument("-N", "--numbers", dest="num_range", help="Command separated range of numbers")
parser.add_argument("configFile", help="Path to config file")
parser.add_argument("cameraName", help="Camera name")
parser.add_argument("directory", help="Directory")
args = parser.parse_args()

if args.configFile is None:
    print("Usage: {0} config-json-file Camera-name Directory".format(sys.argv[0]))
    sys.exit(1)

start_range=1
end_range=9999

file_set = filter_images()
if args.num_range is not None:
    check_numbers()

notify_set = define_relevant_notifications()

neverDrawn = True
model_prob_map = {}

asyncio.get_event_loop().run_until_complete(annotator())
asyncio.get_event_loop().run_forever()

os._exit(1)
