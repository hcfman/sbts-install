#!/usr/bin/python3

import asyncio
import json
import sys
import os

# from threading import Thread
import time

import websockets

from secureparse.model import CameraReader, ReturnResult

#
# Start readers
# enter schedule loop
#

ws_uri = "ws://127.0.0.1:8765"

def processResult(returnResult, reader, resultStr):
    # print("Reader = {0}".format(reader.getName()))
    resultList = json.loads(resultStr)

    # Group into clusters by category
    json_map = {}
    for el in resultList:
        json_map.setdefault(el[0], []).append(el)

    returnResult.setAdvanceSkip(False)
    # for result in resultList:
    categoryMap = reader.getCategoryNotificationListMap()
    for item in json_map.items():
        category = item[0]
        # print("Category found {0}".format(category))
        if category in categoryMap:
            for n in categoryMap[category]:
                n.clearCount()
                for result in item[1]:
                    # print("Checking category")
                    prob = result[1]
                    x, y, w, h = result[2][0], result[2][1], result[2][2], result[2][3]

                    n.checkNotification(returnResult, prob, int(x), int(y), int(w), int(h))

                n.fireNotification(returnResult, prob, int(x), int(y), int(w), int(h))

    print("{0} triggered = {1}, advanceSkip = {2}".format(reader.getName(), returnResult.getTriggered(), returnResult.getAdvanceSkip()))
    return returnResult

async def scheduler():
    returnResultMap = {}
    for reader in readers:
        print("Reader url = {0}".format(reader.getUrl()))
        reader.start()
        returnResultMap[reader.getName()] = ReturnResult()
        print("Joined")

    print("Wait for threads to die")
    readerCount = len(readers)
    readerIndex = 0
    skipped = False
    skipCount = 0

    while True:
        th = readers[readerIndex]
        # print("Call getLastImage")
        lastImage = th.getLastImage()
        # print("Back from call getLastImage")
        if lastImage is not None:
            print("readerIndex = {0}".format(readerIndex))
            print("Check {0}".format(th.getName()))
            # print("Got a lastImage for {0}".format(th.getName()))
            # print("Len lastImage count = {0}".format(lastImage.getCount()))
            # print("Len lastImage = {0}".format(len(lastImage.getImage())))

            try:
                async with websockets.connect(ws_uri) as websocket:
                    skipCount = 0
                    # print("Sending image")
                    await websocket.send(lastImage.getImage())
                    print("Sent image")
                    r = await websocket.recv()
                    print("Received result")

                    print("Result {0}[{1}] = {2}".format(th.getName(), lastImage.getCount(), r))
                    # print()
                    returnResult = processResult(returnResultMap[th.getName()], th, r)

                    if not skipped and returnResult.getAdvanceSkip():
                        skipped = True
                    else:
                        readerIndex = (readerIndex + 1) % readerCount
                        skipped = False

                    # time.sleep(0.65)
            except Exception as e:
                print("Caught exception: {0}", type(e))
                os._exit(1)
        else:
            skipCount += 1
            readerIndex = (readerIndex + 1) % readerCount

        if skipCount == readerCount:
            skipCount = 0
            print("Sleeping")
            time.sleep(0.005)
            print("Woke up")


        print("")

def initialize(configFilename, readers):
    with open(configFilename) as infile:
        data = infile.read();
        configJson = json.loads(data)
        for camera in configJson["cameraList"]:
            readers.append(CameraReader.from_json(camera))

if len(sys.argv) != 2:
    print("Usage: {0} config-json-file".format(sys.argv[0]))
    sys.exit(1)

readers = []
initialize(sys.argv[1], readers)

asyncio.get_event_loop().run_until_complete(scheduler())
asyncio.get_event_loop().run_forever()

print("Exiting...")
os._exit(1)
