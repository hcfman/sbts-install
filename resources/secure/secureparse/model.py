import requests
import time
import threading
from threading import Thread

from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

class CameraReader(Thread):
    def __init__(self, name, url, username, password, categoryNotificationListMap):
        Thread.__init__(self)
        self.lock = threading.Lock()
        self.name = name
        self.url = url
        self.username = username
        self.password = password
        self.lastImage = None
        self.image = None
        self.categoryNotificationListMap = categoryNotificationListMap

    @classmethod
    def from_json(cls, cameraJson) -> 'CameraReader':
        categoryMapJson = cameraJson['categoryMap']
        categoryNotificationListMap = {}
        for category in categoryMapJson.keys():
            categoryNotificationListMap[category] = Notify.notifyListBuilder(categoryMapJson[category]['notifyList'])

        return cls(name=cameraJson['name'],
                   url=cameraJson['url'],
                   username=cameraJson['username'],
                   password=cameraJson['password'],
                   categoryNotificationListMap=categoryNotificationListMap)


    def getLock(self):
        return self.lock

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

    def getCategoryNotificationListMap(self):
        return self.categoryNotificationListMap

    def getLastImage(self):
        self.lock.acquire()
        try:
            returnImage = self.image
            if self.image != None and self.image != self.lastImage:
                self.lastImage = self.image
        finally:
            self.lock.release()

        return returnImage

    def categoryMap(self):
        return self.categoryMap

    def connect(self):
        while True:
            try:
                response = requests.get(self.getUrl(), auth=(self.getUsername(), self.getPassword()), stream=True)
                responseString = str(response)
                print("Response[{0}] = {1}".format(self.getName(), responseString))

                if responseString != '<Response [200]>':
                    break

                stream_bytes = bytes()

                count = 0
                oldTotalTime = time.time()
                t1 = time.time()

                for chunk in response.iter_content(chunk_size=1024):
                    stream_bytes += chunk
                    a = stream_bytes.find(b'\xff\xd8')
                    b = stream_bytes.find(b'\xff\xd9')
                    if a != -1 and b != -1:
                        jpg = stream_bytes[a:b + 2]
                        stream_bytes = stream_bytes[b + 2:]

                        # frame = cv2.imdecode(np.fromstring(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        # cv2.imshow("img", frame)
                        # if cv2.waitKey(1) & 0xFF == ord('q'):
                        #     sys.exit(0)

                        # frame = cv2.imdecode(np.fromstring(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        t1 = time.time()

                        self.lock.acquire()
                        try:
                            self.image = MyImage(jpg, count)
                        finally:
                            self.lock.release()

                        # if count == 200:
                        #     return

                        count += 1
            except Exception as e:
                print("Caught exception reading video: {0}, err: {1}".format(type(e).__name__, str(e)))

            time.sleep(30)


    def run(self):
        self.connect()

class ReturnResult():
    def __init__(self):
        self.triggered = False
        self.lastTriggered = 0
        self.advanceSkip = False

    def setTriggered(self, triggered):
        self.triggered = triggered

    def setLastTriggered(self, lastTriggered):
        self.lastTriggered = lastTriggered

    def setAdvanceSkip(self, advanceSkip):
        self.advanceSkip = advanceSkip

    def getTriggered(self):
        return self.triggered

    def getLastTriggered(self):
        return self.lastTriggered

    def getAdvanceSkip(self):
        return self.advanceSkip

class Counter():
    def __init__(self, min):
        self.min = min

    def getMin(self):
        return self.min

class Notify():
    def __init__(self, zoneName, zoneList, excludeList, url, username, password, method, params, advanceSkip, retryIn, counter):
        self.zoneName = zoneName
        self.zoneList = zoneList
        self.excludeList = excludeList
        self.url = url
        self.username = username
        self.password = password
        self.method = method
        self.params = params
        self.advanceSkip = advanceSkip
        self.retryIn = retryIn
        self.counter = counter
        self._count = 0

    @classmethod
    def from_json(cls, notifyJson:str) -> 'Notify':
        zoneList=[]
        excludeList=[]
        params=[]

        for zone in notifyJson['zoneList']:
            zoneList.append(Zone.zoneListFromJson(zone))
        for zone in notifyJson['excludeList']:
            excludeList.append(Zone.excludeListFromJson(zone))
        params = notifyJson['params']

        min=1
        if "counter" in notifyJson and "min" in notifyJson["counter"]:
            min = notifyJson["counter"]["min"]
        counter = Counter(min=min)

        return cls(zoneName=notifyJson['zoneName'],
                   zoneList=zoneList,
                   excludeList=excludeList,
                   url=notifyJson['url'],
                   username=notifyJson['username'],
                   password=notifyJson['password'],
                   method=notifyJson['method'],
                   params=params,
                   advanceSkip=notifyJson['advanceSkip'],
                   retryIn=notifyJson['retryIn'],
                   counter=counter)

    @classmethod
    def notifyListBuilder(cls, notificationListJson:str):
        notifyList = []
        for notifyJson in notificationListJson:
            notifyList.append(cls.from_json(notifyJson))
        return notifyList

    def clearCount(self):
        self._count = 0

    def _incrementCount(self):
        self._count += 1;

    def _getCount(self):
        return self._count

    def getCounter(self):
        return self.counter

    def getAdvanceSkip(self):
        return self.advanceSkip

    def getRetryIn(self):
        return self.retryIn

    def getZoneList(self):
        return self.zoneList

    def getExcludeList(self):
        return self.excludeList

    def sendNotification(self, prob, x, y, w, h):
        if self.method == "POST":
            requests.post(self.url, auth=(self.username, self.password), data=self.params)
        else:
            requests.get(self.url, auth=(self.username, self.password), data=self.params)

    def isExcluded(self, prob, x, y, w, h):
        basePoint = Point(x, y + h / 2)
        for exclude in self.excludeList:
            region = exclude.getRegion()
            if region.contains(basePoint):
                print("Contained/excluded")
            if prob >= exclude.getConfidence()\
                    and w >= exclude.getMinWidth()\
                    and w < exclude.getMaxWidth()\
                    and h >= exclude.getMinHeight()\
                    and h < exclude.getMaxHeight()\
                    and region.contains(basePoint):
                print("Excluded/Succeeded")
                return True

        print("Excluded/Succeeded")
        return False

    def isIncluded(self, prob, x, y, w, h):
        basePoint = Point(x, y + h / 2)
        for zone in self.zoneList:
            print("checkNotifications prob: {0}, x: {1}, y: {2}, w: {3}, h: {4}".format(prob, x, y, w, h))
            print("n.getConfidence(): {0}, n.getMinWidth(): {1}, n.getMaxWidth(): {2}, n.getMinHeight(): {3}, n.getMaxHeight(): {4}".format(zone.getConfidence(),
                                                                                                                                            zone.getMinWidth(),
                                                                                                                                            zone.getMaxWidth(),
                                                                                                                                            zone.getMinHeight(),
                                                                                                                                            zone.getMaxHeight()))
            region = zone.getRegion()
            if region.contains(basePoint):
                print("Contained/included")
            if prob >= zone.getConfidence()\
                    and w >= zone.getMinWidth()\
                    and w < zone.getMaxWidth()\
                    and h >= zone.getMinHeight()\
                    and h < zone.getMaxHeight()\
                    and region.contains(basePoint):
                print("Included/Succeeded")
                return True

        print("Included/Failed")
        return False

    def checkNotification(self, returnResult:ReturnResult, prob, x, y, w, h):
        print("checkNotifications")
        if self.isExcluded(prob, x, y, w, h):
            return False

        contained = False
        if self.isIncluded(prob, x, y, w, h):
            contained = True
            self._incrementCount()

        return contained


    def fireNotification(self, returnResult:ReturnResult, prob, x, y, w, h):
        print("fireNotification()")
        print("self._getCount() = {0}, self.getCounter().getMin() = {1}".format(self._getCount(), self.getCounter().getMin()))
        if (self._getCount() >= self.getCounter().getMin()):
            if self.getCounter().getMin() > 1:
                print("Counter has higher limit, count of cars => {0}".format(self._getCount()))
            print("It's contained within {0}".format(self.zoneName))
            self.sendNotification(prob, x, y, w, h)
            returnResult.setTriggered(True)
            if self.getAdvanceSkip():
                returnResult.setAdvanceSkip(True)


class Zone():
    def __init__(self, minHeight, maxHeight, minWidth, maxWidth, confidence, region):
        self.minHeight = minHeight
        self.maxHeight = maxHeight
        self.minWidth = minWidth
        self.maxWidth = maxWidth
        self.confidence = confidence
        self.region = region

    @classmethod
    def zoneListFromJson(cls, zoneJson) -> 'Zone':
        region = Region.from_json(regionJson=zoneJson['region'])
        return cls(minHeight=zoneJson['minHeight'],
                              maxHeight=zoneJson['maxHeight'],
                              minWidth=zoneJson['minWidth'],
                              maxWidth=zoneJson['maxWidth'],
                              confidence=zoneJson['confidence'],
                              region=region)

    @classmethod
    def excludeListFromJson(cls, zoneJson) -> 'Zone':
        region = Region.from_json(regionJson=zoneJson['region'])
        return cls(minHeight=zoneJson['minHeight'],
                              maxHeight=zoneJson['maxHeight'],
                              minWidth=zoneJson['minWidth'],
                              maxWidth=zoneJson['maxWidth'],
                              confidence=zoneJson['confidence'],
                              region=region)

    def getName(self):
        return self.name

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

class Region():
    def __init__(self, polygonAsList):
        self.polygonList = polygonAsList
        self.poly = Polygon(polygonAsList)

    @classmethod
    def from_json(cls, regionJson) -> 'Region':
        pointList = []
        for pointJson in regionJson:
            pointItem=(pointJson['x'], pointJson['y'])
            pointList.append(pointItem)
        return cls(pointList)

    def contains(self, p):
        return self.poly.contains(p)

class MyImage():
    def __init__(self, image, count):
        self.image = image
        self.count = count

    def getImage(self):
        return self.image

    def getCount(self):
        return self.count

