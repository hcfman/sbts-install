#!/usr/bin/python3

# Copyright, 2021, Kim Hendrikse

import cv2
import numpy as np

import asyncio
import json
import sys
import os

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

def drawTargetCross(x, y, frame, isIncluded, IsExcluded):
    if isIncluded:
        cv2.putText(frame, "x", (int(x), int(y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, [255, 0, 0], 2)

    if IsExcluded:
        cv2.putText(frame, "x", (int(x), int(y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, [0, 0, 255], 2)

    cv2.imshow("image", frame)
    cv2.waitKey(1)

def drawTarget(category, prob, x, y, w, h, frame):
    xmin, ymin, xmax, ymax = convertBack(float(x), float(y), float(w), float(h))
    pt1 = (xmin, ymin)
    pt2 = (xmax, ymax)
    cv2.rectangle(frame, pt1, pt2, (0, 255, 0), 1)
    cv2.putText(frame, "{0} {1:.2f}".format(category, prob), (pt1[0], pt1[1] + 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, [0, 255, 0], 1)

    cv2.imshow("image", frame)
    cv2.waitKey(1)

async def processResult(frame, resultCache, image, returnResult:ReturnResult, camera:CameraReader):
    returnResult.setAdvanceSkip(False)
    for notify in camera.getNotifyList():
        returnResult.setTriggered(False)

        for zone in notify.getZoneList():
            excluded = False
            excluded = await checkExcluded(frame, excluded, image, resultCache, zone)

            if excluded:
                break

            for include in zone.getIncludeList():
                await checkIncluded(frame, image, include, resultCache, returnResult)

                if returnResult.getTriggered():
                    break

            if returnResult.getTriggered():
                break

async def checkIncluded(frame, image, include, resultCache, returnResult:ReturnResult):
    for modelList in include.getModels():
        triggerCount = 0
        skipping = False
        for model in modelList:
            result = await resultCache.getResult(model.getName(), model.getCategory(), image)

            count = 0
            minCount = model.getCounter()

            for item in result:
                prob = item[1]
                x, y, w, h = item[2][0], item[2][1], item[2][2], item[2][3]
                drawTarget(model.getCategory(), prob, int(x), int(y), int(w), int(h), frame)
                if (model.isContained(prob, int(x), int(y), int(w), int(h))):
                    count += 1

            if count < minCount:
                # minCount is not reached, not enough hits in the current image for this model
                break

            # At this point, there was a hit for this model
            drawTargetCross(int(x), int(y), frame, True, False)
            triggerCount += 1

            if model.getAdvanceSkip():
                skipping = True

        if len(modelList) > 0 and triggerCount == len(modelList):
            # Now all of the models in the inner model list had a valid hit
            returnResult.setTriggered(True)

            if skipping:
                # All the models had a hit and at least one of them required advance skipping
                returnResult.setAdvanceSkip(True)
            break

async def checkExcluded(frame, excluded, image, resultCache, zone):
    for excludeRegion in zone.getExcludeList():
        modelsListList = excludeRegion.getModels()
        for modelList in modelsListList:
            triggerCount = await checkExcludedInnerModelList(frame, image, modelList, resultCache)

            if len(modelList) > 0 and triggerCount == len(modelList):
                excluded = True
                break
    return excluded

async def checkExcludedInnerModelList(frame, image, modelList, resultCache):
    triggerCount = 0
    for model in modelList:
        result = await resultCache.getResult(model.getName(), model.getCategory(), image)

        count = 0
        for item in result:
            prob = item[1]
            x, y, w, h = item[2][0], item[2][1], item[2][2], item[2][3]
            drawTarget(model.getCategory(), prob, int(x), int(y), int(w), int(h), frame)
            if (model.isContained(prob, int(x), int(y), int(w), int(h))):
                count += 1

        if count < model.getCounter():
            # minCount is not reached, not enough hits in the current image for this model
            break

        # At this point, there was a hit for this model
        drawTargetCross(int(x), int(y), frame, False, True)
        triggerCount += 1
    return triggerCount


def readConfigFile():
    with open(args.configFile) as infile:
        data = infile.read();
        configJson = json.loads(data)

        modelMap = ModelMap.from_json(configJson["modelList"])
        cameras = []
        for camera in configJson["cameraList"]:
            if camera["name"] == args.cameraName:
                cameraReader = CameraReader.from_json(camera)
                cameraReader.enable()
                cameras.append(cameraReader)

        return SecureConfig(modelMap.getModelsMap(), cameras)

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

@asyncio.coroutine
def secureRunner():
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
        returnResult = returnResultMap[camera.getName()]

        lastImage = camera.getLastImage()
        if camera.isEnabled() and lastImage is not None:
            resultCache = ResultCache(wsMap)

            try:
                skipCount = 0
                image = lastImage.getImage()
                frame = cv2.imdecode(np.fromstring(lastImage.getImage(), dtype=np.uint8), cv2.IMREAD_COLOR)
                drawRegions(frame, camera)

                yield from processResult(frame, resultCache, image, returnResult, camera)

                if not skipped and returnResult.getAdvanceSkip():
                    skipped = True
                else:
                    cameraIndex = (cameraIndex + 1) % cameraCount
                    skipped = False

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
parser.add_argument("configFile", help="Path to config file")
parser.add_argument("cameraName", help="Camera name")
parser.add_argument("streamUrl", help="Stream URL")
args = parser.parse_args()

if args.configFile is None:
    print("Usage: {0} -u ws_uri config-json-file".format(sys.argv[0]))
    sys.exit(1)

cameraMap = {}
neverDrawn = True

asyncio.get_event_loop().run_until_complete(secureRunner())
asyncio.get_event_loop().run_forever()

os._exit(1)
