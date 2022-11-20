#!/usr/bin/python3

# Copyright, 2021, Kim Hendrikse

import asyncio
from aiohttp import web
import json
import sys
import os

import argparse
import requests

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

async def changeCameraState(request):
    cam = request.match_info.get('cam', "")
    op = request.match_info.get('op', "")

    if not cam in cameraMap.keys() or (op != "enable" and op != "disable"):
        return web.Response(text="Nok")

    if op == "enable":
        cameraMap[cam].enable()
    elif op == "disable":
        cameraMap[cam].disable()

    return web.Response(text="Ok")

async def reportnotifyState(request):
    notifyEnabledMap = {}
    for cam in cameraMap.keys():
        notifyEnabledMap[cam] = {}
        notifyEnabledMap[cam]['enabled'] = cameraMap[cam].isEnabled()
        notifyEnabledMap[cam]['notifications'] = {}
        for notify in cameraMap[cam].getNotifyList():
            notifyEnabledMap[cam]['notifications'][notify.getName()] = notify.isEnabled()

    return web.Response(text=json.dumps(notifyEnabledMap, indent=2), headers={'Content-Type': 'text/json'})

async def changeNotifyState(request):
    cam = request.match_info.get('cam', "")
    notification = request.match_info.get('notification', "")
    op = request.match_info.get('op', "")

    if not cam in cameraMap.keys() or not notification in [notify.getName() for notify in cameraMap[cam].getNotifyList()] \
            or (op != "enable" and op != "disable" and op != "enabled"):
        return web.Response(text="Nok")

    if op == "enable":
        for mapCam in cameraMap[cam].getNotifyList():
            if mapCam.getName() == notification:
                mapCam.enable()
                print("Enable notification {}/{}".format(cam, notification))
                break
    elif op == "disable":
        for mapCam in cameraMap[cam].getNotifyList():
            if mapCam.getName() == notification:
                mapCam.disable()
                print("Disable notification {}/{}".format(cam, notification))
                break

    return web.Response(text="Ok")


async def webServer():

    app = web.Application()
    # app.router.add_get('/', handle)
    app.router.add_post('/enabled', reportnotifyState)
    app.router.add_post('/notify/{op}/{cam}/{notification}', changeNotifyState)
    app.router.add_post('/cam/{op}/{cam}', changeCameraState)
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, server_bind_address, server_port)
    await site.start()

def fireNotification(notify:Notify):
    if debug:
        print("    Fired: {}".format(notify.getName()))
    try:
        if notify.getMethod() == "POST":
            requests.post(notify.getUrl(), auth=(notify.getUsername(), notify.getPassword()), data=notify.getParams())
        else:
            requests.get(notify.getUrl(), auth=(notify.getUsername(), notify.getPassword()), data=notify.getParams())
    except Exception as e:
        print("Caught firing notification: {0}, err: {1}".format(type(e).__name__, str(e)))

async def processResult(resultCache, image, returnResult:ReturnResult, camera:CameraReader):
    returnResult.setAdvanceSkip(False)
    for notify in camera.getNotifyList():
        returnResult.setTriggered(False)

        # Dynamic disable/enable from notifications via rest interface
        # can save process seldom used models
        if not notify.isEnabled():
            continue

        for zone in notify.getZoneList():
            excluded = False
            if debug:
                print("  Zone: {}".format(zone.getName()))
            excluded = await checkExcluded(excluded, image, resultCache, zone)

            if excluded:
                break

            for include in zone.getIncludeList():
                await checkIncluded(image, include, resultCache, returnResult)

                if returnResult.getTriggered():
                    break

            if returnResult.getTriggered():
                break

        if notify.isNegate():
            if not returnResult.getTriggered():
                fireNotification(notify)
        else:
            if returnResult.getTriggered():
                fireNotification(notify)

async def checkIncluded(image, include, resultCache, returnResult:ReturnResult):
    for modelList in include.getModels():
        triggerCount = 0
        skipping = False
        for model in modelList:
            if debug:
                print("    Checking include: {0}, model {1}:{2}".format(include.getName(), model.getName(), model.getCategory()))
            result = await resultCache.getResult(model.getName(), model.getCategory(), image)

            count = 0
            minCount = model.getCounter()

            for item in result:
                prob = item[1]
                x, y, w, h = item[2][0], item[2][1], item[2][2], item[2][3]
                if (model.isContained(prob, int(x), int(y), int(w), int(h))):
                    if debug:
                        print("      {}: matched".format(item))
                    count += 1
                else:
                    if debug:
                        print("      {}".format(item))

            if count < minCount:
                # minCount is not reached, not enough hits in the current image for this model
                break

            # At this point, there was a hit for this model
            triggerCount += 1

            if model.getAdvanceSkip():
                skipping = True

        if len(modelList) > 0 and triggerCount == len(modelList):
            if debug:
                print("    Triggered")
            # Now all of the models in the inner model list had a valid hit
            returnResult.setTriggered(True)

            if skipping:
                # All the models had a hit and at least one of them required advance skipping
                returnResult.setAdvanceSkip(True)
            break

async def checkExcluded(excluded, image, resultCache, zone):
    for excludeRegion in zone.getExcludeList():
        modelsListList = excludeRegion.getModels()
        for modelList in modelsListList:
            triggerCount = await checkExcludedInnerModelList(image, modelList, resultCache)

            if len(modelList) > 0 and triggerCount == len(modelList):
                excluded = True
                break
    return excluded

async def checkExcludedInnerModelList(image, modelList, resultCache):
    triggerCount = 0
    for model in modelList:
        if debug:
            print("    Checking exclude: model {0}:{1}".format(model.getName(), model.getCategory()))
        result = await resultCache.getResult(model.getName(), model.getCategory(), image)

        count = 0
        for item in result:
            prob = item[1]
            x, y, w, h = item[2][0], item[2][1], item[2][2], item[2][3]
            if (model.isContained(prob, int(x), int(y), int(w), int(h))):
                count += 1

        if count < model.getCounter():
            # minCount is not reached, not enough hits in the current image for this model
            break

        # At this point, there was a hit for this model
        triggerCount += 1
    return triggerCount


def readConfigFile():
    with open(args.configFile) as infile:
        data = infile.read();
        configJson = json.loads(data)

        modelMap = ModelMap.from_json(configJson["modelList"])
        cameras = []
        for camera in configJson["cameraList"]:
            cameras.append(CameraReader.from_json(camera))

        return SecureConfig(modelMap.getModelsMap(), cameras)

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
            if debug:
                print("Process camera: {}".format(camera.getName()))
            resultCache = ResultCache(wsMap)

            try:
                skipCount = 0
                image = lastImage.getImage()

                yield from processResult(resultCache, image, returnResult, camera)

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

        if debug:
            print("")


def startCamerasAndInitReturnResult(secureConfig):
    returnResultMap = {}
    cameras = secureConfig.getCameras()
    for camera in cameras:
        if debug:
            print("Reader url = {0}".format(camera.getUrl()))
        camera.start()
        returnResultMap[camera.getName()] = ReturnResult()
        if debug:
            print("Joined")
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
parser.add_argument("-b", "--bind", dest="bind_address", help="Bind address for the control server")
parser.add_argument("-p", "--port", dest="server_port", help="Port for the control server")
parser.add_argument("-d", "--debug", action="store_true", help="Enable debug output")
parser.add_argument("configFile", help="Path to config file")
args = parser.parse_args()

if args.bind_address == None or args.server_port == None:
    print("You must supply both a server bind host address and port")
    sys.exit(1)

server_bind_address = args.bind_address
server_port = args.server_port

if args.configFile is None:
    print("Usage: {0} [-d] -b bind address -p port config-json-file".format(sys.argv[0]))
    sys.exit(1)

debug = args.debug

cameraMap = {}
asyncio.get_event_loop().run_until_complete(webServer())
asyncio.get_event_loop().run_until_complete(secureRunner())
asyncio.get_event_loop().run_forever()

if debug:
    print("Exiting...")

os._exit(1)
