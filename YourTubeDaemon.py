#!/usr/bin/env python2
# encoding: utf-8

#Copyright (C) 2013 by Matthias Stangl
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in
#all copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
#THE SOFTWARE.

import httplib2
import os
import sys
import time
import re
import ConfigParser
import argparse
import logging

from apiclient.errors import HttpError
from apiclient.discovery import build
from subprocess import check_output, CalledProcessError
from oauth2client.file import Storage
from oauth2client.client import flow_from_clientsecrets
from oauth2client.tools import run

""" ParseArgs()
    Return: object with all the cli arguments

    Parse the cli arguments and return them
"""
def ParseArgs():
  parser = argparse.ArgumentParser(description="Your personal YouTube donwload Daemon")
  parser.add_argument("-c", "--config", metavar="PATH", help="Custom config path")
  parser.add_argument("-r", "--rate-limit", metavar="LIMIT",
              help="maximum download rate in bytes per second (e.g. 50K or 4.2M)")
  args = vars(parser.parse_args())
  return args


""" Read_Config(path = None)
        path = Path where the config file is stored (optional)
    Return: Dictionary with the config

    Read the config file from path and initialize the variables
"""
def Read_Config(path = None):
  retConfig = {}

  if path is None:
    if os.getenv("XDG_CONFIG_HOME") is not None:
      path = os.path.join(os.getenv("XDG_CONFIG_HOME",
                                    "YourTubeDaemon/config.cfg"))
    else:
      path = os.path.join(os.path.expanduser("~"),
                          ".config/YourTubeDaemon/config.cfg")
  
  config = ConfigParser.SafeConfigParser()
  config.read(path)

  try:
    retConfig['MusicSavePath'] = config.get("Settings", "MusicSavePath")
    retConfig['CheckIntervalSec'] = config.getint("Settings", "CheckIntervalSec")
    retConfig['LogSavePath'] = config.get("Settings", "LogSavePath")
    retConfig['PlaylistName'] = config.get("Settings", "PlaylistName")
    retConfig['ApiSecretsFile'] = config.get("Settings", "ApiSecretsFile")
    retConfig['RateLimit'] = config.get("Settings", "RateLimit")
  except ConfigParser.Error as e:
    logging.warning("Error while reading config file")
    logging.warning("CONFIG args: {0}".format(e.args))
    logging.warning("CONFIG message: {0}".format(e.message))
    Write_Config()
    retConfig = Read_Config()

  return retConfig


""" Write_Config()

    Used to write the default config file if it is missing and init the variables
"""
def Write_Config():
  if os.getenv("XDG_CONFIG_HOME") is not None:
    defaultPath = os.path.join(os.getenv("XDG_CONFIG_HOME", "YourTubeDaemon"))
  else:
    defaultPath = os.path.join(os.path.expanduser("~"),".config/YourTubeDaemon")
  config = ConfigParser.SafeConfigParser()
  
  config.add_section("Settings")
  config.set("Settings", "MusicSavePath", os.path.join(os.path.expanduser("~"),
                                                      "Music/YourTubeDaemon"))
  config.set("Settings", "CheckIntervalSec", "300")
  config.set("Settings", "LogSavePath", os.path.join(defaultPath, "daemon.log"))
  config.set("Settings", "PlaylistName", "YourTubeDaemon")
  config.set("Settings", "ApiSecretsFile", os.path.join(defaultPath,
                                                        "client_secrets.json"))
  config.set("Settings", "RateLimit", "None")
  
  if not os.path.exists(defaultPath):
    logging.info("Creating default config path: {0}".format(defaultPath))
    os.makedirs(defaultPath)
  with open(os.path.join(defaultPath, "config.cfg"), "w+b") as configFile:
    config.write(configFile)


""" Remove_Unfinished(folder, pattern)
        folder = folder that contains the unfinished files
        pattern = name of the files as regex pattern

    Remove all the unfinished/interrupted downloads of youtube-dl
"""
def Remove_Unfinished(folder, pattern):
  for f in os.listdir(folder):
    if re.search(pattern, f):
      os.remove(os.path.join(folder, f))


""" Format_FileName(input)
        input = InputName which will be formated
    Return: new filename

    Removes all nonalphanumeric chars at the end/beginning
    Removes everything within []
    Removes full, hq, hd, exclusive within ()
"""
def Format_FileName(input):
  # remove everything in []
  reComp = re.compile('(\[.*?\])', re.I)
  input = reComp.sub("", input)

  # remove full, hq, hd, exclusive within ()
  reCompTwo = re.compile('\((FULL|HD|HQ|EXCLUSIVE)\)', re.I)
  input = reCompTwo.sub("", input)

  # remove nonalphanumeric characters at the beginning/end
  reCompThree = re.compile('(^[^\w\(]+)|([^\w\)]+$)', re.I)
  input = reCompThree.sub("", input)
  
  return input


""" Login(CLIENT_SECRETS_FILE = "client_secrets.json")
        CLIENT_SECRETS_FILE = Path to client_secrets file
    Return: SessionId
    
    Login to your YouTube account using client_secrets.json
    Request read/write permission on YouTube
"""
def Login(CLIENT_SECRETS_FILE = "client_secrets.json"):
  MISSING_CLIENT_SECRETS_MESSAGE = """
      You are missing the {0} file!!""".format(CLIENT_SECRETS_FILE)

  YOUTUBE_READ_WRITE_SCOPE = "https://www.googleapis.com/auth/youtube"
  YOUTUBE_API_SERVICE_NAME = "youtube"
  YOUTUBE_API_VERSION = "v3"

  flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
      message=MISSING_CLIENT_SECRETS_MESSAGE,
      scope=YOUTUBE_READ_WRITE_SCOPE)
  
  storage = Storage(os.path.join(
    os.path.dirname(CLIENT_SECRETS_FILE),"{0}-oauth2.json".format(sys.argv[0])))
  credentials = storage.get()
  
  if credentials is None or credentials.invalid:
    credentials = run(flow, storage)
    
  youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
      http=credentials.authorize(httplib2.Http()))

  return youtube

""" Init_Playlist(YOURTUBEDAEMON_PLAYLIST_NAME = "YourTubeDaemon")
        YOURTUBEDAEMON_PLAYLIST_NAME = Name of the playlist (default = YourTubeDaemon)
        youtube = current session variable
    Return: PlaylistId

    Retrives the playlist id of the YourTubeDaemon playlist
    If not available create the YourTubeDaemon playlist
"""
def Init_Playlist(youtube, YOURTUBEDAEMON_PLAYLIST_NAME = "YourTubeDaemon"):
  YOURTUBEDAEMON_PLAYLIST_DESCRIPTION = """
      This playlist is used by YourTubeDaemon to identify the videos to download"""
  
  playlist_list_response = youtube.playlists().list(
    part="id,snippet",
    mine="true"
  ).execute()

  retPlaylist = None
  for playlist in playlist_list_response["items"]:
    if playlist["snippet"]["title"] == YOURTUBEDAEMON_PLAYLIST_NAME:
      retPlaylist = playlist["id"]

  if retPlaylist is None:
    try:
      youtube.playlists().insert(
        part="snippet,status",
        body=dict(
          snippet=dict(
            title=YOURTUBEDAEMON_PLAYLIST_NAME,
            description=YOURTUBEDAEMON_PLAYLIST_DESCRIPTION
        ),
          status=dict(
            privacyStatus="private"
          )
        )
      ).execute()
    except HttpError as e:
      logging.fatal("Init_Playlist: Can't create the playlist")
      logging.fatal("Init_Playlist args: {0}".format(e.args))
      logging.fatal("Init_Playlist message: {0}".format(e.message))
      exit(1)
    time.sleep(1) #give YouTube time to create the playlist

  return retPlaylist


""" Get_Videos(youtube)
        youtube = current session variable
        yourtube_playlistID = Id of the YourTubeDaemon playlist
    Return: list of all videos conataining a list with title, videoId and Id

    Get all the videos in the YourTubeDaemon playlist and return a list
"""
def Get_Videos(youtube, yourtube_playlistID):
  try:
    playlistitems_list_response = youtube.playlistItems().list(
      part="id,snippet",
      playlistId=yourtube_playlistID
    ).execute()
  except HttpError as e:
    logging.error("Get_Videos: Can't get Videos in Playlist")
    logging.error("Get_Videos message: {0}".format(e.message))
    logging.error("Get_Videos args: {0}".format(e.args))
    return None

  videoList = []
  for items in playlistitems_list_response["items"]:
    video = []
    video.append(items["snippet"]["title"])
    video.append(items["snippet"]["resourceId"]["videoId"])
    video.append(items["id"])
    videoList.append(video)

  return videoList


""" main()

    Download audio ranked by best quality
    output name : videoid.fileextensions
    extract audio
    "-f 141/172/38/37/46/45/22/102/101/85/84/171/141/120/100/44/43/35/34/83/82/18/17/6/5/139/36/17"
    "-o '%(id)s.%(ext)s"
    "--extract-audio"
    "--no-continue"
"""
def main():
  YOURTUBEDAEMON_PLAYLIST_ID = None
  SESSION = None
  
  CONFIGPATH = None
  args = ParseArgs()
  if args['config']:
    CONFIGPATH = args['config']
  cfg = Read_Config(CONFIGPATH)

  logging.basicConfig(filename=cfg['LogSavePath'], filemode='w',
                      level=logging.INFO)

  downloadArgs = ["youtube-dl", "-f",
                  "141/172/38/37/46/45/22/102/101/85/84/171/141/120/100/44/43/35/34/83/82/18/17/6/5/139/36/17",
                  "-o", "%(id)s.%(ext)s", "--extract-audio", "--audio-format",
                  "best", "--audio-quality", "0", "--no-continue"]
  if cfg['RateLimit'] != "None" or args['rate_limit']:
    if cfg['RateLimit'] != "None":
      limit = cfg['RateLimit']
    if args['rate_limit']:
      limit = args['rate_limit']
  downloadArgs.extend(["--rate-limit", limit])

  Remove_Unfinished(os.path.dirname(os.path.realpath(__file__)), ".*.part")
  SESSION = Login(cfg['ApiSecretsFile'])
  
  while True:
    videos = Get_Videos(SESSION, YOURTUBEDAEMON_PLAYLIST_ID)
    if videos is None:
      YOURTUBEDAEMON_PLAYLIST_ID = Init_Playlist(SESSION, cfg['PlaylistName'])
      continue

    if len(videos) != 0:
      try:
          for videoItem in videos:
            downloadArgs.extend("http://www.youtube.com/watch?v="+videoItem[1])
            output = check_output(downloadArgs)
            downloadArgs.pop()
            
            regexResult = re.search('(?<=\[ffmpeg\] Destination: )(.*?)(\..{3})', output, re.I)
            newName = Format_FileName(videoItem[0])
            savePath = os.path.join(cfg['MusicSavePath'],newName +
                                    regexResult.group(2))
            logging.info("Downloaded: {0}".format(savePath))

            if not os.path.exists(os.path.dirname(savePath)):
              logging.info("Creating MusicSavePath:{0}".format(cfg['MusicSavePath']))
              os.makedirs(os.path.dirname(savePath))
            os.rename(regexResult.group(0), savePath)
            
            try:
              SESSION.playlistItems().delete(
                id=videoItem[2]
              ).execute()
            except HttpError as e:
              logging.warning("main: Couldn't remove video from playlist")
              logging.warning("main args: {0}".format(e.args))
              logging.warning("main message: {0}".format(e.message))

          videos = []
      except CalledProcessError as e:
        logging.error("Youtube-dl encountered an error")
        logging.error("YT-dl: {0}".format(e.returncode))
        logging.error("YT-dl: {0}".format(e.cmd))
        logging.error("YT-dl: {0}".format(e.output))

    time.sleep(cfg['CheckIntervalSec'])

if __name__ == "__main__":
  main()
