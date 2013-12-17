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

from subprocess import check_output, CalledProcessError
from apiclient.discovery import build
from oauth2client.file import Storage
from oauth2client.client import flow_from_clientsecrets
from oauth2client.tools import run

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


""" Login()
    Return: SessionId
    
    Login to your YouTube account using client_secrets.json
    Request read/write permission on YouTube
"""
def Login():
  CLIENT_SECRETS_FILE = "client_secrets.json"
  MISSING_CLIENT_SECRETS_MESSAGE = """
      You are missing the {0} file in {1}!!""".format(CLIENT_SECRETS_FILE, os.getcwd())

  YOUTUBE_READ_WRITE_SCOPE = "https://www.googleapis.com/auth/youtube"
  YOUTUBE_API_SERVICE_NAME = "youtube"
  YOUTUBE_API_VERSION = "v3"

  flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
      message=MISSING_CLIENT_SECRETS_MESSAGE,
      scope=YOUTUBE_READ_WRITE_SCOPE)
  
  storage = Storage("{0}-oauth2.json".format(sys.argv[0]))
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
    playlist_insert_response = youtube.playlists().insert(
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

  return retPlaylist


""" Get_Videos(youtube)
        youtube = current session variable
        yourtube_playlistID = Id of the YourTubeDaemon playlist
    Return: list of all videos conataining a list with title, videoId and Id

    Get all the videos in the YourTubeDaemon playlist and return a list
"""
def Get_Videos(youtube, yourtube_playlistID):
  playlistitems_list_response = youtube.playlistItems().list(
    part="id,snippet",
    playlistId=yourtube_playlistID
  ).execute()

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

  SESSION = Login()
  YOURTUBEDAEMON_PLAYLIST_ID = Init_Playlist(SESSION)

  while True:
    videos = Get_Videos(SESSION, YOURTUBEDAEMON_PLAYLIST_ID)

    if len(videos) != 0:
      try:
          for videoItem in videos:
            output = check_output(["youtube-dl", "-f",
                "141/172/38/37/46/45/22/102/101/85/84/171/141/120/100/44/43/35/34/83/82/18/17/6/5/139/36/17",
                "-o", "%(id)s.%(ext)s", "--extract-audio", "--audio-format", "best", "--audio-quality", "0",
                "--no-continue", "http://www.youtube.com/watch?v="+videoItem[1]])

            regexResult = re.search('(?<=\[ffmpeg\] Destination: )(.*?)(\..{3})', output, re.I)
            newName = Format_FileName(videoItem[0])
            os.rename(regexResult.group(0), newName + regexResult.group(2))


            playlistitems_delete_response = SESSION.playlistItems().delete(
              id=videoItem[2]
            ).execute()
          
          videos = []
      except CalledProcessError as e:
        print "returncode: {0}".format(e.returncode)
        print " cmd: {0}".format(e.cmd)
        print " output: {0}".format(e.output)

    time.sleep(5) #TODO should be more time (5 * 60)

if __name__ == "__main__":
  main()

#TODO add better comments
#TODO add logging
#TODO add better exception handling
#TODO renove unfinished/interrupted downloads *.part
#TODO add cli options
#TODO add configuration file 
