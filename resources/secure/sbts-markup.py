#!/usr/bin/python3

# Copyright, 2024, Kim Hendrikse

import asyncio
from aiohttp import web
import json
import sys
import os
import subprocess
import argparse
import re
from pathlib import Path
from datetime import datetime

from multi_secureparse.model import SecureConfig, CameraReader, ModelMap

def readConfigFile():
    global parser

    try:
        with open(args.configFile) as infile:
            data = infile.read();
            configJson = json.loads(data)

            modelsMap = ModelMap.from_json(configJson["modelList"]).getModelsMap()
            cameras = {}
            for camera in configJson["cameraList"]:
                cameraReader = CameraReader.from_json(camera)
                cameraReader.enable()
                cameras[cameraReader.getName()] = cameraReader

            return SecureConfig(modelsMap, cameras)
    except FileNotFoundError:
        print("Configuration file not found.")
        sys.exit(1)
    except PermissionError:
        print("Insufficient permissions to read the configuration file.")
        sys.exit(1)


async def run_subprocess_async(command):
    process = await asyncio.create_subprocess_shell(command)
    await process.wait()

async def markupWithAnnotations(request):
    global cameras, debug

    cam = request.match_info.get('cam', "")
    cam_name = request.match_info.get('camName', "")
    image_range = request.match_info.get('range', "")

    data = await request.post();
    eventTime = data.get('eventTime')
    if cam is None or not re.match('^\d+$', cam):
        print("Bad cam")
        return web.Response(text='Nok')

    notification = request.match_info.get('notification', "")
    if notification is None or len(notification) == 0 or re.match('.*["\'].*$', notification):
        return web.Response(text='Nok')

    if eventTime is None or not re.match('^\d+$', eventTime):
        return web.Response(text='Nok')

    date_string = datetime.fromtimestamp(int(int(eventTime) / 1000)).strftime('%Y-%m-%d')

    if not Path(args.image_dir + "/" + cam).exists():
        return web.Response(text='Nok')

    if cam_name is None or not cam_name in cameras:
        return web.Response(text='Nok')

    if notification not in notify_map[cam_name]:
        return web.Response(text='Nok')

    command = args.sbts_annotate + " -N " + image_range + " -n " + notification + " " + args.configFile + " " + cam_name + " " + args.image_dir + "/" + cam + "/" + date_string + "/" + eventTime
    if debug:
        print("Command: {0}".format(command))

    await run_subprocess_async(command)

    return web.Response(text="Ok")

async def webServer():
    global cameras, notify_map

    secureConfig = readConfigFile()
    cameras = secureConfig.getCameras()
    notify_map = {};
    for camera in cameras:
        for cam in cameras:
            notify_map[cam] = {}
            for notify in cameras[cam].getNotifyList():
                notify_map[cam][notify.getName()] = notify

    app = web.Application()
    app.router.add_post('/markup/{cam}/{camName}/{range}/{notification}', markupWithAnnotations)
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, server_bind_address, server_port)
    await site.start()

async def main():
    await webServer()
    while True:
        await asyncio.sleep(3600)

parser = argparse.ArgumentParser()
parser.add_argument("-b", "--bind", dest="bind_address", help="Bind address for the control server")
parser.add_argument("-p", "--port", dest="server_port", help="Port for the control server")
parser.add_argument("-d", "--debug", action="store_true", help="Enable debug output")
parser.add_argument("sbts_annotate", help="Path to sbts-annotate.py")
parser.add_argument("configFile", help="Path to config file")
parser.add_argument("image_dir", help="Path to image directory")

# parser.add_argument("images_path", help="Path to images directory")
args = parser.parse_args()
debug=args.debug
if args.bind_address == None or args.server_port == None:
    print("You must supply both a server bind host address and port")
    sys.exit(1)

server_bind_address = args.bind_address
server_port = args.server_port

if args.configFile is None:
    print("Usage: {0} [-d] -b bind address -p port config-json-file".format(sys.argv[0]))
    sys.exit(1)

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
