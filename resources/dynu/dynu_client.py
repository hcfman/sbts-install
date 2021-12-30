#!/usr/bin/python3

import configparser
import requests
import re
import hashlib
import os

configParser = configparser.RawConfigParser()
configFilePath = os.getenv('HOME') + '/sbts-local/dynuParams.config'
configParser.read(configFilePath)

dynuUpdateUrl = configParser.get('dynuParams', 'dynuUpdateUrl')
hostName = configParser.get('dynuParams', 'hostName')
myipv6 = configParser.get('dynuParams', 'myipv6')
username = configParser.get('dynuParams', 'username')
ipSources = configParser.get('dynuParams', 'ipSources')
password = configParser.get('dynuParams', 'password')

print("Dynu Client Started")
try:
    m = hashlib.md5()
    m.update(password.encode('utf-8'))
    md5Password = m.hexdigest()
    print(md5Password)

    for ipSource in ipSources.split(","):
        print("IP fetching source - "+ipSource)
        response = requests.get(ipSource)
        ip = response.json()["ip"]
        print("IP found - "+ip)
        if (re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip)):
            break;

    print("Started updating IP in Dynu")
    response = requests.get(url=dynuUpdateUrl,
                            params={"hostname": hostName, "myip": ip, "myipv6": myipv6, "username": username,
                                    "password": md5Password})
    print("Response from Dynu - "+str(response.content))
except Exception as e:
    print("Caught exception whilst sending to sbts, exception: {0}, err: {1}".format(type(e).__name__, e.__str__()))
