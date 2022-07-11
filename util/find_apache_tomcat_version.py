#!/usr/bin/python3

# Copyright (c) 2022 Kim Hendrikse

import sys
import re
from ftplib import FTP

def callBack(line):
    print("In callback")
    print("Line = \"{}\"".format(line))

def findVersion():
    TOMCAT_PATH='internet/apache/tomcat/tomcat-9'

    ftp = FTP('ftp.nluug.nl')

    # internet/apache/tomcat/tomcat-9/v9.0.44/bin/
    ftp.login()

    ftp.cwd('pub')
    ftp.cwd(TOMCAT_PATH)
    data = ftp.nlst()
    # apache-tomcat-9.0.44.tar.gz
    data.sort(reverse=True)

    if (len(data) <= 0):
        sys.exit(1)

    version=data[0]
    ftp.cwd(version + "/bin")
    data = ftp.nlst()
    elements=filter(lambda x: re.match(r'apache-tomcat-9\.[\d\.]*\.tar.gz', x), data)
    ftp.quit()

    try:
        tar_file=next(elements)
        full_path = 'ftp.nluug.nl' '/' + TOMCAT_PATH + '/' + version + '/bin/' + tar_file
        print("https://{}".format(full_path))
    except StopIteration:
        print("Can't find a version of tomcat9")
        sys.exit(1)


findVersion()
