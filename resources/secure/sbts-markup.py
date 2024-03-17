#!/usr/bin/python3

# Copyright, 2024, Kim Hendrikse

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
import subprocess

from aiohttp import web

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

async def run_script(command):
    # This is a coroutine that runs the script and waits for it to finish.
    process = await asyncio.create_subprocess_exec(*command, stdout=None, stderr=None)
    await process.wait()

async def start_background_tasks(app):
    app['queue'] = asyncio.Queue()
    # Use asyncio.ensure_future for compatibility with Python 3.6
    app['script_runner_task'] = asyncio.ensure_future(script_runner(app))

async def cleanup_background_tasks(app):
    app['script_runner_task'].cancel()
    await app['script_runner_task']

async def script_runner(app):
    while True:
        # Wait indefinitely until an item is available in the queue.
        command = await app['queue'].get()
        await run_script(command)
        # Mark the current task as done.
        app['queue'].task_done()


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

    command = [args.sbts_annotate, '-N',  image_range, '-n', notification, args.configFile, cam_name, args.image_dir + "/" + cam + "/" + date_string + "/" + eventTime]
    if debug:
        print("Command: {0}".format(command))

    await request.app['queue'].put(command)

    return web.Response(text="Ok")

def webServer():
    global app

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

    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)

    web.run_app(app, host=args.bind_address, port=int(server_port))

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
    webServer()

os._exit(1)
