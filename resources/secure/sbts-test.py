#!/usr/bin/python3

# Copyright, 2021, Kim Hendrikse

import cv2
import numpy as np

import asyncio
import json
import sys
import os
import re

import argparse

import websockets

from multi_secureparse.model import SecureConfig, CameraReader, Notify, ModelMap

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

class ReturnResult():
    def __init__(self):
        self.triggered = False
        self.advanceSkip = False

    def setTriggered(self, triggered):
        self.triggered = triggered

    def setAdvanceSkip(self, advanceSkip):
        self.advanceSkip = advanceSkip

    def getTriggered(self):
        return self.triggered

    def getAdvanceSkip(self):
        return self.advanceSkip

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

def drawTarget(category, prob, x, y, w, h, frame):
    xmin, ymin, xmax, ymax = convertBack(float(x), float(y), float(w), float(h))
    pt1 = (xmin, ymin)
    pt2 = (xmax, ymax)
    cv2.rectangle(frame, pt1, pt2, (0, 255, 0), 1)
    cv2.putText(frame, "{0} {1:.2f}".format(category, prob), (pt1[0], pt1[1] + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, [0, 255, 0], 1)

    # cv2.imshow("image", frame)
    # cv2.waitKey(1)

async def checkIncluded(frame, image, include, resultCache, included:bool):
    global neverDrawn;

    for modelList in include.getModels():
        triggerCount = 0
        for model in modelList:
            result = await resultCache.getResult(model.getName(), model.getCategory(), image)

            count = 0
            for item in result:
                neverDrawn = False
                prob = item[1]
                x, y, w, h = item[2][0], item[2][1], item[2][2], item[2][3]
                drawTarget(model.getCategory(), prob, int(x), int(y), int(w), int(h), frame)
                if (model.isContained(prob, int(x), int(y), int(w), int(h))):
                    count += 1

                    if count > 0:
                        drawTargetCross(int(x), int(y), frame, included)
                        triggerCount += 1


async def processResult(frame, resultCache, image, camera:CameraReader):
    for notify in camera.getNotifyList():
        for zone in notify.getZoneList():
            for include in zone.getIncludeList():
                await checkIncluded(frame, image, include, resultCache, True)

            for include in zone.getExcludeList():
                await checkIncluded(frame, image, include, resultCache, False)

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
                cameraReader.setUrl(args.streamUrl)
                cameraReader.enable()
                cameras.append(cameraReader)

        return SecureConfig(modelsMap, cameras)

def drawRegions(frame, camera):
    global neverDrawn

    for notify in camera.getNotifyList():
        for zone in notify.getZoneList():
            for include in zone.getIncludeList():
                for modelList in include.getModels():
                    for model in modelList:
                        pts = np.array(model.getPolygon().getPointList(), np.int32)
                        cv2.polylines(frame, [pts], True, (0, 255, 255))

            for exclude in zone.getExcludeList():
                for modelList in exclude.getModels():
                    for model in modelList:
                        pts = np.array(model.getPolygon().getPointList(), np.int32)
                        cv2.polylines(frame, [pts], True, (0, 0, 255))

    if neverDrawn:
        cv2.imshow("image", frame)
        cv2.waitKey(1)
        neverDrawn = False


@asyncio.coroutine
def secureTester():
    # Read the configuration json file
    secureConfig = readConfigFile()

    # Start the camera reader threads and initialise the return result
    cameras, returnResultMap = startCamerasAndInitReturnResult(secureConfig)

    # Create websocket connections for the models
    wsMap = yield from initWebsocketMap(secureConfig)

    cameraCount = len(cameras)
    cameraIndex = 0
    skipped = False
    skipCount = 0

    while True:
        camera = cameras[cameraIndex]

        lastImage = camera.getLastImage()
        if camera.isEnabled() and lastImage is not None:
            resultCache = ResultCache(wsMap)

            try:
                skipCount = 0
                image = lastImage.getImage()
                frame = cv2.imdecode(np.fromstring(lastImage.getImage(), dtype=np.uint8), cv2.IMREAD_COLOR)
                drawRegions(frame, camera)

                yield from processResult(frame, resultCache, image, camera)
                cv2.imshow("image", frame)
                cv2.waitKey(100)

            except Exception as e:
                print("Caught exception: {0}", type(e))
                os._exit(1)
        else:
            skipCount += 1
            cameraIndex = (cameraIndex + 1) % cameraCount

        if skipCount == cameraCount:
            skipCount = 0
            yield from asyncio.sleep(0.005)

def startCamerasAndInitReturnResult(secureConfig):
    returnResultMap = {}
    cameras = secureConfig.getCameras()
    for camera in cameras:
        camera.start()
        returnResultMap[camera.getName()] = ReturnResult()
        cameraMap[camera.getName()] = camera
    return cameras, returnResultMap


def initWebsocketMap(secureConfig):
    wsMap = {}
    for modelName in secureConfig.getModelsMap().keys():
        modelsMap = secureConfig.getModelsMap()
        modelMapJson = modelsMap[modelName]
        url = modelMapJson['url']
        ws = yield from websockets.connect(url)
        wsMap[modelName] = ws
    return wsMap


def initialize(configFilename, readers):
    with open(configFilename) as infile:
        data = infile.read();
        configJson = json.loads(data)
        for camera in configJson["cameraList"]:
            readers.append(CameraReader.from_json(camera))

parser = argparse.ArgumentParser()
parser.add_argument("-m", "--model-list", dest="model_list", help="List of models and their websocket urls")
parser.add_argument("configFile", help="Path to config file")
parser.add_argument("cameraName", help="Camera name")
parser.add_argument("streamUrl", help="Stream URL")
args = parser.parse_args()

if args.configFile is None:
    print("Usage: {0} config-json-file Camera-name Stream-Url".format(sys.argv[0]))
    sys.exit(1)

cameraMap = {}
neverDrawn = True

asyncio.get_event_loop().run_until_complete(secureTester())
asyncio.get_event_loop().run_forever()

os._exit(1)
