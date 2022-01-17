# Copyright, 2021, Kim Hendrikse

import os
import requests
import time
import threading
from threading import Thread

from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

class ModelMap():
    def __init__(self, modelsMap):
        self.modelsMap = modelsMap

    @classmethod
    def from_json(cls, modelList) -> 'ModelMap':
        modelsMap = {}
        for key in modelList.keys():
            modelsMap[key] = {"url":modelList[key]['url']}

        return cls(modelsMap = modelsMap)

    def getModelsMap(self) -> 'dict':
        return self.modelsMap

    def getModelUrl(self, name):
        return self.modelsMap[name]["url"]

class Notify():
    def __init__(self, name, zoneList:list, url, username, password, method, params, enabled):
        self.lock = threading.Lock()
        self.name = name
        self.zoneList = zoneList
        self.url = url
        self.username = username
        self.password = password
        self.method = method
        self.params = params
        self.enabled = enabled

    @classmethod
    def from_json(cls, polygonDict, notifyJson) -> 'Notify':
        if 'name' in notifyJson.keys() and "/" in notifyJson['name']:
            print("You cannot use / in a notification name, you used {}".format(notifyJson['name']))
            os._exit(1)

        zoneList=[]

        for zone in notifyJson['zoneList']:
            zoneList.append(Zone.zoneFromJson(polygonDict, zone))
        params = notifyJson['params']

        # Can be set here, but intended to be set dynamically via the rest interface
        if 'enabled' in notifyJson.keys():
            enabled = notifyJson['enabled']
        else:
            enabled = True

        return cls(name=notifyJson['name'],
                   zoneList=zoneList,
                   url=notifyJson['url'],
                   username=notifyJson['username'],
                   password=notifyJson['password'],
                   method=notifyJson['method'],
                   params=params,
                   enabled=enabled)

    @classmethod
    def notifyListBuilder(cls, notificationListJson):
        notifyList = []
        for notifyJson in notificationListJson:
            notifyList.append(cls.from_json(notifyJson))
        return notifyList

    def getName(self):
        return self.name

    def getZoneList(self) -> 'list:Zone':
        return self.zoneList

    def getUrl(self):
        return self.url

    def getUsername(self):
        return self.username

    def getPassword(self):
        return self.password

    def getMethod(self):
        return self.method

    def getParams(self):
        return self.params

    def enable(self):
        self.lock.acquire()
        try:
            self.enabled = True
        finally:
            self.lock.release()

    def disable(self):
        self.lock.acquire()
        try:
            self.enabled = False
        finally:
            self.lock.release()

    def isEnabled(self):
        enabled = True
        self.lock.acquire()
        try:
            enabled = self.enabled
        finally:
            self.lock.release()

        return enabled

class CameraReader(Thread):
    def __init__(self, name, url, username, password, polygonDict, notifyList, enabled):
        Thread.__init__(self)
        self.lock = threading.Lock()
        self.enabled = True
        self.name = name
        self.url = url
        self.username = username
        self.password = password
        self.polygonDict = polygonDict
        self.lastImage = None
        self.image = None
        self.notifyList = notifyList
        self.enabled = enabled

    @classmethod
    def from_json(cls, cameraJson) -> 'CameraReader':
        # Can be set here, but intended to be set dynamically via the rest interface
        if 'enabled' in cameraJson.keys():
            enabled = cameraJson['enabled']
        else:
            enabled = True

        polygonDict = {}
        if "polygonDict" in cameraJson.keys():
            for key in cameraJson["polygonDict"]:
                polygon = cameraJson["polygonDict"][key]
                if isinstance(polygon, list):
                    sbtsPolygon = SbtsPolygon.from_json(polygon)
                    polygonDict[key] = sbtsPolygon
        notifyList = []
        for notify in cameraJson['notifyList']:
            notifyList.append(Notify.from_json(polygonDict, notify))

        return cls(name=cameraJson['name'],
                   url=cameraJson['url'],
                   username=cameraJson['username'],
                   password=cameraJson['password'],
                   polygonDict=polygonDict,
                   notifyList=notifyList,
                   enabled=enabled)

    def isEnabled(self):
        self.lock.acquire()
        try:
            enabled = self.enabled
        finally:
            self.lock.release()
        return enabled

    def enable(self):
        self.lock.acquire()
        try:
            self.enabled = True
        finally:
            self.lock.release()

    def disable(self):
        self.lock.acquire()
        try:
            self.enabled = False
        finally:
            self.lock.release()

    def getName(self):
        return self.name

    def getUrl(self):
        return self.url

    def setUrl(self, url):
        self.url = url

    def getUsername(self):
        return self.username

    def getPassword(self):
        return self.password

    def getImage(self):
        return self.image

    def getNotifyList(self) -> 'list:Notify':
        return self.notifyList

    def getLastImage(self):
        self.lock.acquire()
        try:
            if self.image != None and self.image != self.lastImage:
                self.lastImage = self.image
                returnImage = self.lastImage
            else:
                returnImage = None
        finally:
            self.lock.release()

        return returnImage

    def connect(self):
        while True:
            if self.isEnabled():
                try:
                    response = requests.get(self.getUrl(), auth=(self.getUsername(), self.getPassword()), stream=True)
                    responseString = str(response)

                    if responseString != '<Response [200]>':
                        break

                    print("Connected to \"{}\"".format(self.getName()))

                    stream_bytes = bytes()

                    count = 0
                    oldTotalTime = time.time()
                    t1 = time.time()

                    for chunk in response.iter_content(chunk_size=1024):
                        if not self.isEnabled():
                            response.close()
                            print("Disconnect from \"{}\"".format(self.getName()))
                            break

                        stream_bytes += chunk
                        a = stream_bytes.find(b'\xff\xd8')
                        b = stream_bytes.find(b'\xff\xd9')
                        if a != -1 and b != -1:
                            jpg = stream_bytes[a:b + 2]
                            stream_bytes = stream_bytes[b + 2:]

                            self.lock.acquire()
                            try:
                                self.image = MyImage(jpg, count)
                            finally:
                                self.lock.release()

                            count += 1
                except Exception as e:
                    print("Caught exception reading video from {}, {}: {}, err: {}".format(self.getName(), self.getUrl(), type(e).__name__, str(e)))

            time.sleep(30)

    def run(self):
        self.connect()

class Zone():
    def __init__(self, name:str, includeList:list, excludeList:list):
        self.name = name
        self.includeList = includeList
        self.excludeList = excludeList

    @classmethod
    def zoneFromJson(cls, polygonDict, zoneJson) -> 'Zone':
        includeList = []
        excludeList = []

        for includeJson in zoneJson['includeList']:
            includeList.append(Include.from_json(polygonDict, includeJson))
        for include in zoneJson['excludeList']:
            excludeList.append(Include.from_json(polygonDict, include))
        return cls(name=zoneJson['name'],
                   includeList=includeList,
                   excludeList=excludeList)

    def getName(self):
        return self.name

    def getIncludeList(self) -> 'list:Include':
        return self.includeList

    def getExcludeList(self):
        return self.excludeList

    def getMinHeight(self):
        return self.minHeight

    def getMaxHeight(self):
        return self.maxHeight

    def getMinWidth(self):
        return self.minWidth

    def getMaxWidth(self):
        return self.maxWidth

    def getConfidence(self):
        return self.confidence

    def getRegion(self):
        return self.region

    def contains(self, p):
        return self.getRegion().contains(p)

class Include():
    def __init__(self, name, models):
        self.name = name
        self.models = models

    @classmethod
    def from_json(cls, polygonDict, includeJson) -> 'Include':
        modelListList=[]

        for modelListJson in includeJson['models']:
            modelList = []
            for modelJson in modelListJson:
                model = Model.from_json(polygonDict, modelJson)
                modelList.append(model)
            modelListList.append(modelList)

        return cls(includeJson['name'], modelListList)

    def getName(self) -> 'str':
        return self.name

    def getModels(self) -> 'list:Model':
        return self.models

class Model():
    def __init__(self, name:str, category:str, minHeight:float, maxHeight:float,
                 minWidth:float, maxWidth:float,
                 confidence:float,
                 advanceSkip: bool,
                 counter: int = None,
                 namedPolygon: str = None,
                 polygon: list = []):
        self.name = name
        self.category = category
        self.minHeight = minHeight
        self.maxHeight = maxHeight
        self.minWidth = minWidth
        self.maxWidth = maxWidth
        self.confidence = confidence
        self.advanceSkip = advanceSkip
        self.counter = counter
        self.namedPolygon = namedPolygon,
        self.polygon = polygon

    @classmethod
    def from_json(cls, polygonDict, modelJson) -> 'Model':
        advanceSkip = True
        if 'advanceSkip' in modelJson.keys() is not None:
            advanceSkip = modelJson['advanceSkip']
        if 'counter' in modelJson.keys():
            counter = modelJson['counter']
        else:
            counter = 1

        if not ('polygon' in modelJson.keys() or 'namedPolygon' in modelJson.keys()):
            print("You must specify one of \"namedPolygon\" or \"polygon\", aborting...")
            os._exit(1)

        if 'polygon' in modelJson.keys():
            polygon=SbtsPolygon.from_json(modelJson['polygon'])

        # Override polygon with dictionary value if found
        namedPolygon = None
        if 'namedPolygon' in modelJson.keys():
            namedPolygon = modelJson["namedPolygon"]
            if not namedPolygon in polygonDict.keys():
                print("Polygon with name \"{}\" not found in polygonDict, aborting...".format(namedPolygon))
                os._exit(1)
            else:
                polygon = polygonDict[namedPolygon]

        return cls(name=modelJson['name'],
                   category=modelJson['category'],
                   minHeight=modelJson['minHeight'],
                   maxHeight=modelJson['maxHeight'],
                   minWidth=modelJson['minWidth'],
                   maxWidth=modelJson['maxWidth'],
                   confidence=modelJson['confidence'],
                   advanceSkip=advanceSkip,
                   counter=counter,
                   polygon=polygon,
                   namedPolygon=namedPolygon
                   )

    def getName(self):
        return self.name

    def getCategory(self):
        return self.category

    def getMinHeight(self):
        return self.minHeight

    def getMaxHeight(self):
        return self.maxHeight

    def getMinWidth(self):
        return self.minWidth

    def getMaxWidth(self):
        return self.maxWidth

    def getConfidence(self):
        return self.confidence

    def getAdvanceSkip(self):
        return self.advanceSkip

    def getCounter(self):
        return self.counter

    def getNamedPolygon(self):
        return self.namedPolygon

    def getPolygon(self) -> 'SbtsPolygon':
        return self.polygon

    def isContained(self, prob, x, y, w, h) -> 'bool':
        basePoint = Point(x, y + h / 2)

        if prob >= self.getConfidence()\
                and w >= self.getMinWidth()\
                and w < self.getMaxWidth()\
                and h >= self.getMinHeight()\
                and h < self.getMaxHeight()\
                and self.getPolygon().contains(basePoint):
            return True

        return False

class SbtsPolygon():
    def __init__(self, pointList):
        self.pointList = pointList
        self.poly = Polygon(pointList)

    @classmethod
    def from_json(cls, polygonJson) -> 'SbtsPolygon':
        pointList = []
        for pointJson in polygonJson:
            pointItem = (pointJson['x'], pointJson['y'])
            pointList.append(pointItem)
        return cls(pointList)

    def contains(self, p):
        return self.poly.contains(p)

    def getPointList(self):
        return self.pointList

    def getPoly(self):
        return self.poly

class MyImage():
    def __init__(self, image, count):
        self.image = image
        self.count = count

    def getImage(self):
        return self.image

    def getCount(self):
        return self.count

class SecureConfig():
    def __init__(self, modelsMap, cameras):
        self.modelsMap = modelsMap
        self.cameras = cameras

    def getModelsMap(self):
        return self.modelsMap

    def getCameras(self):
        return self.cameras

