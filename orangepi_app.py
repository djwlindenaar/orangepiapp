#!/usr/bin/python3

#import pyttsx
#say = pyttsx.init()

import tkinter as tk
import tkinter.ttk as ttk
from mpd import MPDClient
import os
import time
import threading
import optparse
#import cv2
from PIL import Image, ImageTk
#import pygame.camera as cam
#import pygame.image as pgimage

from io import BytesIO
import base64

from subprocess import Popen
import signal

from datetime import datetime
from basiciw import iwinfo

import sys

import asynchat
import asyncore
import socket
import logging
import logging.handlers

#import bluetooth
import json
import select

import re
 
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyPKCE

import json

secrets = json.load(open(os.path.expanduser("~/secrets.json")))

chat_room = {}

global client


TITLE_FONT = ("Helvetica", 20, "")
CLOCK_FONT = ("BMW Type Automotive", 24, "")
INFO_FONT = ("BMW Type Automotive", 20, "")
SMALL_FONT = ("Courier", 14, "bold")
MEDIUM_FONT = ("Courier", 14, "bold")
LARGE_FONT = ("Courier", 20, "bold")

class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """
    def __init__(self, logger, log_level=logging.INFO):
       self.logger = logger
       self.log_level = log_level
       self.linebuf = ''
 
    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        pass

class SampleApp(tk.Tk):

    def __init__(self, *args, **kwargs):
        tk.Tk.__init__(self, *args, **kwargs)
        #bg = "#999966"
        #bg = "#42412D"
        #bg = "#4a453a"
        bg = "#42454a"
        bg = "#32353a"
        bg = "#22252a"
        bg = "#201C1C"
        #bg = "black"
        select = "orange"
        fg = "white"

        style = ttk.Style()
        style.layout('Treeview.Row',[("Treerow.trough",{'sticky':'nwse','children':[('Treeitem.row', {'sticky': 'nswe'})]})])
        style.configure(".", font=('Arial', 16), foreground=fg)
        style.configure("Treeview", 
            foreground = fg, fieldbackground=bg, background=bg, rowheight=30,
            borderwidth = 3, relief='flat')
        style.configure("Row", troughrelief='flat', padding=10)
        style.configure("Item", padding=5)
        style.map("Treeview", 
            foreground= [('selected', fg)], 
            background=[], 
            #font=[('selected',('Arial',16,'bold')),('!selected',('Arial',16,''))]
            )
        style.map("Row", 
            troughcolor = [('!selected', 'black'),('selected', select)], 
            borderwidth = [('selected',4),('!selected',0)])
        style.configure("TLabel",background=bg, foreground = fg)
        style.configure("TFrame",background=bg, foreground = fg)
        self.frames = {}
        self.state = {'state':'Paused', 'volume': 50}
        self.handler = sink()
        self.bind("<<PAUSE>>", self.Pause)
        self.bind("<<UNPAUSE>>", self.Unpause)
        self.bind("<<VOLUP>>", self.Volup)
        self.bind("<<VOLDOWN>>", self.Voldown)
        self.bind("<<Notification>>", lambda event: self.show_frame(NotificationPage))

        self.sp = None
        self.spdevice = None
        # the container is where we'll stack a bunch of frames
        # on top of each other, then the one we want visible
        # will be raised above the others
        self.configure(background=bg)
        container = ttk.Frame(self, padding=(10,0,0,0))
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=0, minsize=380)
        container.grid_columnconfigure(0, weight=0, minsize=840)

        for F in (StartPage, MenuPage, BrowserPage, NotificationPage):
            frame = F(container, self)
            self.frames[F] = frame
            # put all of the pages in the same location;
            # the one on the top of the stacking order
            # will be the one that is visible.
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame(StartPage)

    def show_frame(self, c):
        '''Show a frame for the given class'''
        for cls,frame in self.frames.items():
            if cls == c:
                frame = self.frames[c]
                frame.tkraise()
                frame.focus_set()
                frame.raised()
            else:
                frame.lowered()
    
    def Pause(self, event):
        global client
        print("Got Pause")
        if self.sp is None:
            client.pause(1)
        else:
            self.sp.pause_playback()

    def Unpause(self, event):
        global client
        print("Got Unpause")
        if self.sp is None:
            client.pause(0)
        else:
            if self.spdevice is None:
                self.spdevice = [device['id'] for device in self.sp.devices()['devices'] if device['name']=='BMW'][0]
            self.sp.transfer_playback(self.spdevice)

    def Volup(self, event):
        global client
        print("Got VolUp")
        status = client.status()
        client.setvol(int(status['volume'])+5)

    def Voldown(self, event):
        global client
        print("Got VolDown")
        status = client.status()
        client.setvol(int(status['volume'])-5)


class StartPage(ttk.Frame):

    def __init__(self, parent, controller):
        ttk.Frame.__init__(self, parent)
        self.controller = controller
        self.volts = " 0.00"
        self.temp = " 0"
        
        self.BTConnected = False

        self.album = ttk.Label(self, text="title", font=TITLE_FONT)
        self.title = ttk.Label(self, text="title", font=TITLE_FONT)
        self.artist = ttk.Label(self, text="title", font=TITLE_FONT)
        self.nextlabel = ttk.Label(self, text="Up next:", font=MEDIUM_FONT)
        self.nextsong = [ttk.Label(self, text="title", font=SMALL_FONT) for n in range(5)]
        self.time = ttk.Label(self, text="title", font=CLOCK_FONT)
        self.date = ttk.Label(self, text="title", font=CLOCK_FONT)
        self.state = ttk.Label(self, text="title", font=TITLE_FONT)
        self.flags = ttk.Label(self, text="title", font=TITLE_FONT)
        
        self.infoframe = tk.Frame(self, height=300)
        self.infoframe.place(relx=0, rely=0, x=700, y=100, anchor='ne')
        self.infolabel=[]
        self.info=[' ']*7
        for n in range(len(self.info)):
            self.infolabel.append(ttk.Label(self.infoframe, text=".", anchor='se', font=INFO_FONT))
            self.infolabel[n].pack(fill='x', anchor='se')
        
        self.album.grid         (row=0, column=0, columnspan=10, sticky="w", padx=10)
        self.artist.grid        (row=1, column=0, columnspan=10, sticky="w", padx=10)
        self.title.grid         (row=2, column=0, columnspan=10, sticky="w", padx=10)
        self.nextlabel.grid     (row=3, column=0, columnspan=10, sticky="ws", padx=10)
        for cnt,item in enumerate(self.nextsong):
            item.grid     (row=6+cnt, column=0, columnspan=10, sticky="w", padx=10)
        self.time.grid          (row=20, column=0, columnspan=1, sticky="sw", padx=10)
        self.state.grid         (row=20, column=1, columnspan=1, sticky="sw", padx=10)
        self.flags.grid         (row=20, column=2, columnspan=1, sticky="sw", padx=10)
        self.date.place(relx=0, rely=0, x=700, y=342, anchor='ne')
        self.grid_columnconfigure(0, minsize = 200)
        self.grid_columnconfigure(1, minsize = 150)
        self.grid_columnconfigure(2, minsize = 50)
        self.grid_columnconfigure(3, minsize = 160)
        self.grid_columnconfigure(4, minsize = 50)
        self.grid_columnconfigure(9, weight = 1)
        self.grid_rowconfigure(20,weight=1)
        self.grid_rowconfigure(3,minsize=40)
        
        self.actions = ttk.Frame(self)
        self.wifiimage = [
            tk.PhotoImage(file='/usr/share/pixmaps/wifi_off.gif'),
            tk.PhotoImage(file='/usr/share/pixmaps/wifi.gif'),
        ]
        self.btimage = [
            tk.PhotoImage(file='/usr/share/pixmaps/bt_off.gif'),
            tk.PhotoImage(file='/usr/share/pixmaps/bt.gif'),
        ]
        self.actionimages = [
            [ 
                tk.PhotoImage(file='/usr/share/pixmaps/media-play.gif'),
                tk.PhotoImage(file='/usr/share/pixmaps/media-play-active.gif'),
                tk.PhotoImage(file='/usr/share/pixmaps/media-play-selected.gif')
            ],
            [ 
                tk.PhotoImage(file='/usr/share/pixmaps/media-restart.gif'),
                tk.PhotoImage(file='/usr/share/pixmaps/media-restart-active.gif'),
                tk.PhotoImage(file='/usr/share/pixmaps/media-restart-selected.gif')
            ],
            [
                tk.PhotoImage(file='/usr/share/pixmaps/media-skip.gif'),
                tk.PhotoImage(file='/usr/share/pixmaps/media-skip-active.gif'),
                tk.PhotoImage(file='/usr/share/pixmaps/media-skip-selected.gif')
            ],
            [
                tk.PhotoImage(file='/usr/share/pixmaps/media-seek.gif'),
                tk.PhotoImage(file='/usr/share/pixmaps/media-seek-active.gif'),
                tk.PhotoImage(file='/usr/share/pixmaps/media-seek-selected.gif')
            ],
        ]
        self.actionlabels = [
            ttk.Label(self.actions, image=self.actionimages[0][0]),
            ttk.Label(self.actions, image=self.actionimages[1][2]),
            ttk.Label(self.actions, image=self.actionimages[2][2]),
            ttk.Label(self.actions, image=self.actionimages[3][2]),
        ] 
        self.actionnames = [
            'play pause',
            'restart',
            'skip',
            'seek'
        ]
        for thelabel in self.actionlabels:
            thelabel.pack(side=tk.LEFT)
        self.wifilabel = ttk.Label(self.actions, image=self.wifiimage[0])
        self.wifilabel.pack(side=tk.LEFT)
        self.btlabel = ttk.Label(self.actions, image=self.btimage[0])
        self.btlabel.pack(side=tk.LEFT)

        self.actions.place(x=10, y=275)
        self.actionactive = 0
        self.actionselected = 0
        self.actionupdate()
        
        self.update_clock()
        
        self.bind("<Escape>", lambda event: controller.show_frame(MenuPage))
        self.bind("<<Notification>>", lambda event: controller.show_frame(NotificationPage))
        self.bind("<Return>", self.click)
        self.bind("<Up>", self.Up)
        self.bind("<Down>", self.Down)


    def actionupdate(self):
        if self.actionselected < 0:
            self.actionselected = len(self.actionlabels)-1
        elif self.actionselected >= len(self.actionlabels):
            self.actionselected = 0
        for n, label in enumerate(self.actionlabels):
            if n==self.actionselected:
#                if say.isBusy():
#                    say.stop()
#                say.say(self.actionnames[n])
                label.configure(image = self.actionimages[n][1 if self.actionactive>0 else 2])
            else:
                label.configure(image = self.actionimages[n][0])

    def click(self, event):
        global client
        if self.actionactive == 0:
            self.actionactive = 10
            if self.actionselected == 0:
                self.actionactive = 0
                #self.status = client.status()
                if self.controller.sp is not None:
                    if self.status['state']=='stop' or self.status['state']=='pause':
                        if self.controller.spdevice is None:
                            self.controller.spdevice = [device['id'] for device in self.controller.sp.devices()['devices'] if device['name']=='BMW'][0]
                        self.controller.sp.transfer_playback(self.controller.spdevice)
                    else:
                        self.controller.sp.pause_playback()
                else:
                    if self.status['state']=='stop':
                        client.play()
                    else:
                        client.pause()
                self.update_clock(False)
            elif self.actionselected == 1:
                self.actionactive = 0
                #self.status = client.status()
                if self.status['state']=='play':
                    client.seekcur('0')
                self.update_clock(False)
        else:
            self.actionactive = 0
        self.actionupdate()

    def Up(self, event):
        global client
        if self.actionactive == 0:
            self.actionselected -= 1
            self.actionupdate()
        else:
            self.actionactive = 10
            if self.actionselected == 2:
                self.status = client.status()
                if self.status['state']=='stop':
                    client.play()
                client.previous()
                self.update_clock(False)
            elif self.actionselected == 3:
                client.seekcur('-10')
                self.update_clock(False)
        
    def Down(self, event):
        global client
        if self.actionactive == 0:
            self.actionselected += 1
            self.actionupdate()
        else:
            self.actionactive = 10
            if self.actionselected == 2:
                self.status = client.status()
                if self.status['state']=='stop':
                    client.play()
                client.next()
                self.update_clock(False)
            elif self.actionselected == 3:
                client.seekcur('+10')
                self.update_clock(False)
    
    def raised(self):
        self.actionupdate()
        pass
    
    def lowered(self):
        pass
    
    def update_clock(self, restart=True):
        global client
        if restart:
            self.controller.after(500, self.update_clock)
            if self.actionactive > 0:
                self.actionactive -= 1
                if self.actionactive == 0:
                    self.actionselected = 0
                    self.actionupdate()
        try:
            self.status = client.status()
        except:
            try:
                client.disconnect()
            except:
                pass
            try:
                client.connect(client.host, 6600)
                self.status = client.status()
            except:
                self.title.configure(text="MPD connection error!")
                return
        try:
            if iwinfo('wlan1')['essid'] == 'ZyXEL73B680':
                self.wifilabel.configure(image = self.wifiimage[1])
            else:
                self.wifilabel.configure(image = self.wifiimage[0])
        except:
            pass
        
        self.btlabel.configure(image = self.btimage[1 if self.BTConnected else 0])
        if self.controller.sp is not None:
            try:
                status = self.controller.sp.current_playback()
                if self.controller.spdevice is None:
                    self.controller.spdevice = [device['id'] for device in self.controller.sp.devices()['devices'] if device['name']=='BMW'][0]
                    self.controller.sp.transfer_playback(self.controller.spdevice, False)
                #print(self.controller.spdevice)
                #print(status)
                self.status = {
                    'volume': '100',
                    'repeat': '0', 
                    'random': '0', 
                    'single': '0', 
                    'consume': '0', 
                    'partition': 
                        'default', 
                    'playlist': '2', 
                    'playlistlength': '0', 
                    'mixrampdb': '0', 
                    'state': 'play' if status['is_playing'] else 'pause',
                    'songid': [{'title': status['item']['name'], 'artist': status['item']['artists'][0]['name'], 'album':status['item']['album']['name']}],
                    'time': "%d:%d" % (status['progress_ms']/1000, status['item']['duration_ms']/1000)
                }
            except:
                self.status = {
                    'volume': '100',
                    'repeat': '0', 
                    'random': '0', 
                    'single': '0', 
                    'consume': '0', 
                    'partition': 'default', 
                    'playlist': '2', 
                    'playlistlength': '0', 
                    'mixrampdb': '0', 
                    'state': 'stop'
            }

            
        if int(self.status['playlistlength']) > 1000:
                client.clear()
                self.update_clock(False)
                return

        time = datetime.now().strftime('%H:%M')
        self.date.configure(text='%5s'%time)
        for label,info in zip(self.infolabel, self.info):
            label.configure(text=info) 
        
        if 'songid' in self.status:
            if self.controller.sp is not None:
                song = self.status['songid'][0]
            else:
                song = client.playlistid(self.status['songid'])[0]
            self.title.configure(text=song['title'] if 'title' in song else "")
            self.artist.configure(text=song['artist'] if 'artist' in song else "")
            self.album.configure(text=song['album'] if 'album' in song else "")
        else:
            self.title.configure(text="")
            self.artist.configure(text="")
            self.album.configure(text="")
        if 'time' in self.status: 
            time = [int(t) for t in self.status['time'].split(':')]
            self.time.configure(text="%3d:%02d / %d:%02d" % (
                        time[0]/60,time[0]%60, time[1]/60,time[1]%60))
        else:
            self.time.configure(text="")
        statetext={
            "pause":"Paused",
            "stop":"Stopped",
            "play":"Playing",
        }
        self.state.configure(text=statetext[self.status['state']])
        self.flags.configure(text=
            ("R" if self.status['repeat']=='1' else "_") +
            ("S" if self.status['random']=='1' else "_") +
            ("C" if self.status['consume']=='1' else "_") +
            ("U" if 'updating_db' in self.status else "_") +
            "")

        if 'nextsongid' in self.status and self.status['random']=='1':
            song = client.playlistid(self.status['nextsongid'])[0]
            for item in self.nextsong:
                item.configure(text="")
            self.nextsong[0].configure(text= (
                ("" if 'artist' not in song else song['artist']) +
                " - " +
                song['title']))
        elif 'song' in self.status and self.status['random']=='0':
            cursong = int(self.status['song'])
            songs = client.playlistinfo("%d:"%(cursong+1))
            for item in self.nextsong:
                item.configure(text="")
            for song,item in zip(songs,self.nextsong):
                item.configure(text= (
                    ("" if 'artist' not in song else song['artist'] + " - ") +
                    ("" if 'title' not in song else song['title'])))
        else:
            for item in self.nextsong:
                item.configure(text="")


class MenuPage(ttk.Frame):

    def __init__(self, parent, controller):
        ttk.Frame.__init__(self, parent)
        self.controller = controller
        label = ttk.Label(self, text="Menu", font=TITLE_FONT)
        label.pack(side="top", fill="x", pady=10)
        self.tree = ttk.Treeview(self, show="")
        self.tree["columns"]=("name","type")
        self.tree["displaycolumns"]=("0")
        self.tree.column("name",minwidth=500,width=500, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=1)
        self.tree.bind("<Return>", self.entertree)
        self.tree.bind("<Escape>", self.esctree)
        self.tree.bind("<<TreeviewSelect>>", self.selection)
        self.path = ""
        self.tree.insert("","end", text = "Browse", values = ["Browse"])
        self.tree.insert("","end", text = "SpotifyL", values=["Start spotify Liesbeth"])
        self.tree.insert("","end", text = "SpotifyD", values=["Start spotify Daniel"])
        self.tree.insert("","end", text = "StopSpotify", values=["Stop spotify"])
        self.random = self.tree.insert("","end", text = "Random", values = ["Turn random on"])
        self.repeat = self.tree.insert("","end", text = "Repeat", values = ["Turn repeat on"])
        self.tree.insert("","end", text = "Update", values = ["Update DB"])
        self.tree.insert("","end", text = "Video", values = ["Video"])
        self.tree.insert("","end", text = "Diagnostics", values=["Turn diagnostic mode on"])
        self.tree.insert("","end", text = "EngineLogger", values=["Start engine logger"])
        self.tree.insert("","end", text = "Notifications", values = ["Notifications"])
        selection = self.tree.get_children()[0]
        self.tree.selection_set(selection)
        self.tree.focus(selection)
        self.tree.see(selection)
        self.spotify = None

    def selection(self, event=None):
        item = self.tree.selection()
        box = self.tree.bbox(item)
        itemname = self.tree.item(item,'text')
#        if say.isBusy():
#            say.stop()
#        say.say(itemname)
    
    
    def raised(self):
        global client
        self.tree.focus_set()
        self.status = client.status()
        self.tree.item(self.random, values=["Turn random "+("on" if self.status['random']=='0' else "off")])
        self.tree.item(self.repeat, values=["Turn repeat "+("on" if self.status['repeat']=='0' else "off")])
        self.selection()

    def lowered(self):
        pass
    
    def stopspotify(self):
        if self.spotify is not None:
            try:
                self.spotify.send_signal(signal.SIGINT)
            except:
                pass
        self.spotify = None
        self.controller.sp = None
        
        
    def entertree(self, event):
        global client
        selection = self.tree.selection()
        item = self.tree.item(selection, "text")
        if item == "Browse":
            self.controller.show_frame(BrowserPage)
        elif item == "Notifications":
            self.controller.show_frame(NotificationPage)
        elif item == "Update":
            client.update("/")
            self.controller.show_frame(StartPage)
        elif item == "Random":
            self.status = client.status()
            client.random(1-int(self.status['random']))
            self.tree.item(self.random, values=["Turn random "+("on" if self.status['random']=='1' else "off")])
        elif item == "Repeat":
            self.status = client.status()
            client.repeat(1-int(self.status['repeat']))
            self.tree.item(self.repeat, values=["Turn repeat "+("on" if self.status['repeat']=='1' else "off")])
        elif item == "Video":
            pass
            #self.controller.show_frame(PageVideo)
        elif item == "Diagnostics":
            if "off" in self.tree.item(selection, "values")[0]:
                self.controller.handler.push("Diagnostics: off\n".encode())
                self.tree.item(selection, values=["Turn diagnostic mode on"]) 
            else: 
                self.controller.handler.push("Diagnostics: on\n".encode())
                self.tree.item(selection, values=["Turn diagnostic mode off"]) 
        elif item == "EngineLogger":
            #self.controller.handler.push("Diagnostics: on\n".encode())
            Popen([sys.executable, '/usr/local/bin/enginelogbt.py'])
        elif item == "SpotifyL":
            client.pause(1)
            self.stopspotify()
            # Set up the Spotify authentication
            try:
                self.controller.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=secrets['SPOTIPY_CLIENT_ID'],
                                                               client_secret=secrets['SPOTIPY_CLIENT_SECRET'],
                                                               redirect_uri=secrets['SPOTIPY_REDIRECT_URI'],
                                                               username=secrets['liesbeth']['username'],
                                                               open_browser=False,
                                                               scope='user-read-playback-state,user-modify-playback-state,user-read-currently-playing,playlist-read-private,user-library-read'))
                self.spotify = Popen(['/usr/bin/librespot','-O','-n','BMW','-u', secrets['liesbeth']['username'], '-p', secrets['liesbeth']['password'], '-m', 'softvol', '-R', '100'])
                self.controller.spdevice = None
            except Exception as error:
                print("An error occurred:", error) # An error occurred: name 'x' is not defined
                self.stopspotify()
            self.controller.show_frame(StartPage)
        elif item == "SpotifyD":
            client.pause(1)
            self.stopspotify()
            # Set up the Spotify authentication
            try:
                self.controller.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=secrets['SPOTIPY_CLIENT_ID'],
                                                               client_secret=secrets['SPOTIPY_CLIENT_SECRET'],
                                                               redirect_uri=secrets['SPOTIPY_REDIRECT_URI'],
                                                               username=secrets['daniel']['username'],
                                                               open_browser=False,
                                                               scope='user-read-playback-state,user-modify-playback-state,user-read-currently-playing,playlist-read-private,user-library-read'))
                self.spotify = Popen(['/usr/bin/librespot','-O','-n','BMW','-u', secrets['daniel']['username'], '-p', secrets['daniel']['password'], '-m', 'softvol', '-R', '100'])
                self.controller.spdevice = None
            except Exception as error:
                print("An error occurred:", error) # An error occurred: name 'x' is not defined
                self.stopspotify()
            #print(self.controller.sp.me())
            #print(self.controller.sp.devices())
            self.controller.show_frame(StartPage)
        elif item == "StopSpotify":
            self.stopspotify()
            self.controller.show_frame(StartPage)

    def esctree(self, event):
        self.controller.show_frame(StartPage)
    
    def filltree(self, selection = 0):
        pass

class BrowserPage(ttk.Frame):

    def __init__(self, parent, controller):
        ttk.Frame.__init__(self, parent)
        self.controller = controller
        label = ttk.Label(self, text="Browse", font=TITLE_FONT)
        label.pack(side="top", fill="x", pady=10)
        self.tree = ttk.Treeview(self, show="")
        self.tree["columns"]=("name","type","symbol")
        self.tree["displaycolumns"]=("2","0")
        self.tree.column("name",minwidth=0,width=200, anchor="w")
        self.tree.column("symbol",minwidth=20,width=20, stretch="no", anchor="e")
        self.tree.pack(fill=tk.BOTH, expand=1)
        self.tree.bind("<Return>", self.entertree)
        self.tree.bind("<Escape>", self.esctree)
        self.tree.bind("<<TreeviewSelect>>", self.selection)
        self.path = ""
        self.selections = []
        self.filltree()

    def selection(self, event=None):
        target = 5
        item = self.tree.selection()
        box = self.tree.bbox(item)
        if len(box)==0:
            pos = target
            self.controller.after_idle(self.selection)
        else:
            pos=int(box[1]/box[3])
        while (pos < target):
            self.tree.yview_scroll(-1,'units')
            pos += 1
        while pos > target:
            self.tree.yview_scroll(1, 'units')
            pos -= 1
        itemname = self.tree.item(item,'values')[0]
#        if say.isBusy():
#            say.stop()
#        say.say(itemname)
    
    def raised(self):
        print("raised")
        self.path = ""
        self.selections = []
        self.tree.delete(*self.tree.get_children())
        self.filltree()
        self.tree.focus_set()
        
    def lowered(self):
        pass
    
    def entertree(self, event):
        global client
        self.path = self.tree.item(self.tree.selection(), "text")
        itemdata = self.tree.item(self.tree.selection(), "values")
        if itemdata[1] == "directory":
            self.selections.append(self.tree.index(self.tree.selection()))
            #self.path += "/" + item 
            print(self.path)
            self.tree.delete(*self.tree.get_children())
            self.filltree()
        elif itemdata[1] == "playthis":
            client.clear()
            client.add(self.path)
            client.play()
            self.controller.show_frame(StartPage)
        elif itemdata[1] == "addthis":
            client.add(self.path)
        else:
            self.selections.append(self.tree.index(self.tree.selection()))
            #self.path += "/" + item 
            print(self.path)
            self.tree.delete(*self.tree.get_children())
            self.filltree()
            #client.add(self.path)
    
    def esctree(self, event):
        if len(self.selections) > 0:
            self.path = os.path.dirname(self.path) 
            
            print(self.path)
            self.tree.delete(*self.tree.get_children())
            self.filltree(self.selections.pop())
        else:
            self.controller.show_frame(MenuPage)
        if len(self.selections) == 0:
            self.path=""
    
    def filltree(self, selection = 0):
        global client
        dirlist = client.lsinfo("/" if len(self.path)==0 else self.path)
    
        self.tree.insert("","end", text = self.path, values = ["Play this","playthis",""])
        self.tree.insert("","end", text = self.path, values = ["Add this","addthis",""])
        dirs = []
        allnumeric = True
        for item in dirlist:
            if 'directory' in item:
                dirs.append(item['directory'])
                if not os.path.basename(item['directory']).isnumeric():
                    allnumeric = False

        if len(self.path)>0:
            if allnumeric:
                dirs.sort(reverse=True)
            else:
                dirs.sort()

        for item in dirs:
            self.tree.insert("","end", text = item, values = [os.path.basename(item),"directory",">"])
        for item in dirlist:
            if 'file' in item:
                if 'title' in item:
                    self.tree.insert("","end", text = item['file'], values = [item["title"],"song",'\u266A'])
                else:
                    self.tree.insert("","end", text = item['file'], values = [item['file'],"song",'\u266A'])
        selected = self.tree.get_children()[selection]
        self.tree.selection_set(selected)
        self.tree.focus(selected)
        self.tree.see(selected)

#class PageVideo(ttk.Frame):
#
#    def __init__(self, parent, controller):
#        ttk.Frame.__init__(self, parent)
#        self.controller = controller
#        self.label = ttk.Label(self)
#        self.label.pack(side="top", fill="both", pady=10)
#        imgtk = ImageTk.PhotoImage('RGB',(640,360))
#        self.imgtk = imgtk
#        self.label.configure(image=self.imgtk)
#        self.visible = False
#        cam.init()
#        cam.list_cameras()
#        try:
#            self.cam = cam.Camera("/dev/video0", (640,480))
#        except:
#            self.cam = None
#        self.bind("<Escape>", lambda event: controller.show_frame(StartPage))
#        self.bind("<<Notification>>", lambda event: controller.show_frame(NotificationPage))
#
#    def show_frame(self, auto = True):
#        if not self.visible:
#            return
#        img = self.cam.get_image()
#        imgtk = ImageTk.PhotoImage(Image.fromstring('RGB',(640,360),pgimage.tostring(img, 'RGB')))
#        self.imgtk = imgtk
#        self.label.configure(image=self.imgtk)
#        if auto:
#            self.after(100, self.show_frame)
#
#    def raised(self):
#        if self.cam is None:
#            self.controller.show_frame(StartPage)
#        else:
#            self.visible = True 
#            try:
#                self.cam.start()
#                self.show_frame()
#            except:
#                self.visible = False
#                self.controller.show_frame(StartPage)
#
# 
#    def lowered(self):
#        if self.visible:
#            self.cam.stop()
#        self.visible = False

class NotificationPage(ttk.Frame):

    def __init__(self, parent, controller):
        ttk.Frame.__init__(self, parent)
        self.controller = controller
        self.title = ttk.Label(self, text="Notifications")
        self.title.pack(side="top", fill="both", pady=10)
        self.label = ttk.Label(self)
        self.label.pack(side="top", fill="both", pady=10)
        self.label2 = ttk.Label(self, wraplength=700, anchor='nw', justify='left')
        self.label2.pack(side="top", fill="both", expand=1, pady=10)
        self.label3 = ttk.Label(self)
        self.label3.pack(side="top", fill="both", pady=10)
        self.visible = False
        self.bind("<Escape>", lambda event: controller.show_frame(StartPage))
        self.bind("<Up>", lambda event: self.show_text(self.shown+1))
        self.bind("<Down>", lambda event: self.show_text(self.shown-1))

        self.item = []
        self.shown = 0

    def show_text(self, which=10000000):
        if which >= len(self.item):
            which = len(self.item)-1
        if which < 0:
            which = 0

        if len(self.item)>0:
            self.label.configure(\
                text=time.strftime('%H:%M:%S ',time.localtime(self.item[which]['notification']['when']/1000)) +\
                self.item[which]['appName']+\
                ": "+\
                self.item[which]['notification']['title'] + '\n' +\
                self.item[which]['notification']['tickerText'] + \
                '')
            self.label2.configure(text=self.item[which]['notification']['text'])
            try:
                #try to add the image...
                img = Image.open(BytesIO(base64.b64decode(self.item[which]['icon'].replace('\\n',''))))
                img = img.resize((100,100),Image.ANTIALIAS)
                self.img = ImageTk.PhotoImage(img)
                self.label3.configure(image=self.img)
            except:
                pass

            self.shown = which
    
    def raised(self):
        self.show_text()
 

 
    def lowered(self):
        self.visible = False

class ChatHandler(asynchat.async_chat):
    def __init__(self, sock, app):
        asynchat.async_chat.__init__(self, sock=sock, map=chat_room)
 
        self.set_terminator(b'\n')
        self.buffer = []
        self.power = 0
        self.aux = 1 #CCC adaptation
        self.keymap = {
            "UP":"<Up>",
            "DOWN":"<Down>",
            "VOLUP":"<<VOLUP>>",
            "VOLDOWN":"<<VOLDOWN>>",
            "MENU":"<Escape>",
            "CLICK":"<Return>",
        }

        self.app = app
 
    def collect_incoming_data(self, data):
        self.buffer.append(bytes.decode(data))
 
    def found_terminator(self):
        msg = ''.join(self.buffer)
        print("Received: %s"%msg)
        state = self.app.frames[StartPage].status['state']
        print("State: %s"%state)
        if msg in self.keymap.keys():
            self.app.event_generate(self.keymap[msg], when="tail")
            self.push(('got %s-key \n' % msg).encode())
        elif 'Power' in msg:
            if ('On' in msg) and (self.power == 0):
                self.power = 1
                #say = pyttsx.init()
                if self.aux == 1:
                    self.app.event_generate("<<UNPAUSE>>", when="tail")
                    #client.pause(0)
            elif ('Off' in msg):
                self.power = 0 
                self.app.event_generate("<<PAUSE>>", when="tail")
                #client.pause(1)
        elif 'Aux' in msg:
            if ('On' in msg) and (self.aux == 0):
                self.aux = 1
                if self.power == 1:
                    self.app.event_generate("<<UNPAUSE>>", when="tail")
                    #client.pause(0)
            elif ('Off' in msg):
                self.aux = 0 
                self.app.event_generate("<<PAUSE>>", when="tail")
                #client.pause(1)
        elif 'Volts' in msg:
            self.app.frames[StartPage].info[0] = '%s V'%msg.split(': ')[1]
        elif 'ETemp' in msg:
            self.app.frames[StartPage].info[1] = '%s C'%msg.split(': ')[1]
        elif 'ITemp' in msg:
            self.app.frames[StartPage].info[2] = '%s C'%msg.split(': ')[1]
        elif 'Torque' in msg:
            self.app.frames[StartPage].info[3] = '%s Nm'%msg.split(': ')[1]
        elif 'EnginePwr' in msg:
            self.app.frames[StartPage].info[4] = '%s kW'%msg.split(': ')[1]
        elif 'Consume' in msg:
            self.app.frames[StartPage].info[5] = '%s ml/km'%msg.split(': ')[1]
        elif 'SatSpeed' in msg:
            self.app.frames[StartPage].info[6] = '%s km/h'%msg.split(': ')[1]
        elif 'Consumption' in msg:
            pass
        else:        
            self.push(str.encode(msg + '\n'))
        self.buffer = []
 
class sink():
    def __init__(self):
        pass
    
    def push(self, msg):
        pass

class ChatServer(asyncore.dispatcher):
    def __init__(self, server_address, app):
        asyncore.dispatcher.__init__(self, map=chat_room)
       # Make sure the socket does not already exist
        try:
            os.unlink(server_address)
        except OSError:
            if os.path.exists(server_address):
                raise 
        self.create_socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.bind(server_address)
        self.app = app
        self.listen(5)
 
    def handle_accept(self):
        pair = self.accept()
        print(pair)
        if pair is not None:
            sock, addr = pair
            handler = ChatHandler(sock, self.app)
            self.app.handler = handler

def buffered_readlines(sock, buf_size=4096):
    """
    pull_next_chunk is callable that should accept one positional argument max_len,
    i.e. socket.recv or file().read and returns string of up to max_len long or
    empty one when nothing left to read.

    >>> for line in buffered_readlines(socket.recv, 16384):
    ...     print line
        ...
    >>> # the following code won't read whole file into memory
    ... # before splitting it into lines like .readlines method
    ... # of file does. Also it won't block until FIFO-file is closed
    ...
    >>> for line in buffered_readlines(open('huge_file').read):
    ...     # process it on per-line basis
                ...
    >>>
    """
    chunks = []
    while True:
        ready_to_read, ready_to_write, in_error = \
               select.select(
                  [sock],
                  [],
                  [],
                  1)
        if len(ready_to_read)==0:
            if len(in_error)>0:
                print("Socket is in error!")
                raise ValueError
            continue
        chunk = ready_to_read[0].recv(buf_size)
        if not b'\r\n' in chunk:
            chunks.append(chunk)
            continue
        chunk = chunk.split(b'\r\n')
        if chunks:
            yield b''.join(chunks + [chunk[0]])
        else:
            yield chunk[0]
        for line in chunk[1:-1]:
            yield line
        if chunk[-1]:
            chunks = [chunk[-1]]
        else:
            chunks = []

#def connect_btspp():
#    btlogger = logging.getLogger('btlog')
#    uuid = "00001101-0000-1000-8000-00805f9b34fb"
#    while True:
#        service_matches = bluetooth.find_service(  address = '94:65:2D:87:F0:76',uuid = uuid )
#        #service_matches = []
#        sock=bluetooth.BluetoothSocket( bluetooth.RFCOMM )
#        if len(service_matches) == 0:
#            btlogger.info("couldn't find the smartphone service")
#            time.sleep(5)
#            continue
#        else:
#            for first_match in service_matches:
#                port = first_match["port"]
#                name = first_match["name"]
#                host = first_match["host"]
#                if name == 'btspp':
#                    btlogger.info("connecting to \"%s\" on %s" % (name, host))
#            
#                    try:
#                        sock.connect((host, port))
#                        sock.settimeout(0.0)
#                        return sock
#                    except:
#                        time.sleep(5)
#                        continue

re_pattern = re.compile(u'[^\u0000-\uD7FF\uE000-\uFFFF]', re.UNICODE)

def filter_unicode(unicode_string):
    return re_pattern.sub(u'\uFFFD', unicode_string)

#def bluez_notifier(app):
#    btlogger = logging.getLogger('btlog')
#    
#    app.frames[StartPage].BTConnected = False
#    sock=connect_btspp()
#    app.frames[StartPage].BTConnected = True
#    while(True):
#        try:
#            for line in buffered_readlines(sock):
#                try:
#                    #btlogger.info(line)
#                    message = json.loads(line.decode("utf-8"))
#                except ValueError:
#                    btlogger.info('JSON error...')
#                    btlogger.info(line)
#                btlogger.info(repr(message.keys()) + ' - ' + message['event'])
#                if message['event']=='notificationRemoved':
#                    continue
#                elif message['event']=='notificationPosted':
#    
#                    item = message['eventItems'][0]
#                    #btlogger.info(item)
#                    btlogger.info(item['notification'].keys())
#
#                    for key in ['tickerText','text','title']:
#                        if key not in item['notification'].keys():
#                            item['notification'][key] = ""
#                        else:
#                            item['notification'][key] = filter_unicode(item['notification'][key])
#
#                    btlogger.info(time.strftime('%H:%M ',time.localtime(item['notification']['when']/1000)) +\
#                        item['appName']+\
#                        ": "+\
#                        item['notification']['tickerText'] + ' - ' +\
#                        item['notification']['title'] +\
#                        '')
#                        
#                    btlogger.info(item['notification']['text'])
#                    app.frames[NotificationPage].item.append(item)
#                    app.event_generate('<<Notification>>', when="tail")
#
#                    #dismiss = {}
#                    #dismiss['event']='dismiss'
#                    #dismiss['notification'] = {'key':item['key']}
#                    #btlogger.info(json.dumps(dismiss))
#                    #sock.send((json.dumps(dismiss)+'\r\n').encode("utf-8"))
#                    #btlogger.info(b"{\"event\":\"dismiss\",\"notification\":{\"key\":\""+item['key'].encode('utf-8')+b"\"}}\r\n")
#                    #sock.send(b"{\"event\":\"dismiss\",\"notification\":{\"key\":\""+item['key'].encode('utf-8')+b"\"}}\r\n")
#    
#        except KeyboardInterrupt:
#            raise
#        except  ValueError:
#            btlogger.info("Value error: ")
#            app.frames[StartPage].BTConnected = False
#            sock=connect_btspp()
#            app.frames[StartPage].BTConnected = True
#                
#        except bluetooth.btcommon.BluetoothError as eargs:
#            btlogger.info("bluetooth error: ")
#            app.frames[StartPage].BTConnected = False
#            sock=connect_btspp()
#            app.frames[StartPage].BTConnected = True

if __name__ == "__main__":
    parser = optparse.OptionParser(
        usage = "%prog [options] [port [baudrate]]",
        description = "Simple Serial to Network (TCP/IP) redirector.",
    )
    
    parser.add_option("-q", "--quiet",
        dest = "quiet",
        action = "store_true",
        help = "suppress non error messages",
        default = False
    )

    parser.add_option("-H", "--host",
        dest = "host",
        help = "MPD host",
        default = "127.0.0.1"
    )

    parser.add_option("-p", "--passwd",
        dest = "passwd",
        help = "MPD password",
        default = None
    )

    parser.add_option("-s", "--socket",
        dest = "socket",
        help = "Socket to create for communication with can app",
        default = "/var/run/sockfile",
        )
    
    (options, args) = parser.parse_args()

    if options.quiet:
        stdout_logger = logging.getLogger('log')
        stdout_logger.setLevel(logging.DEBUG)
        handler = logging.handlers.RotatingFileHandler(
              '/tmp/appdbg.log', maxBytes=1e7, backupCount=5)
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        stdout_logger.addHandler(handler)
        handler = logging.handlers.RotatingFileHandler(
              '/tmp/appwarn.log', maxBytes=1e7, backupCount=5)
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(logging.WARN)
        stdout_logger.addHandler(handler)

        sys.stdout = StreamToLogger(stdout_logger, logging.DEBUG)
        sys.stderr = StreamToLogger(stdout_logger, logging.WARN)
    
    btlogger = logging.getLogger('btlog')
    btlogger.setLevel(logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler(
            '/tmp/bt.log', maxBytes=1e7, backupCount=5)
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d: %(levelname)s: %(name)s: %(message)s',datefmt="%H:%M:%S")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    btlogger.addHandler(handler)
    
    client = MPDClient()               # create client object
    client.timeout = 10                # network timeout in seconds (floats allowed), default: None
    client.idletimeout = None          # timeout for fetching the result of the idle command is handled seperately, default: None
    client.connect(options.host, 6600)  # connect to localhost:6600
    client.host = options.host
    if options.passwd is not None:
        client.password(options.passwd)
    app = SampleApp()
    server = ChatServer(options.socket, app)
     
    comm = threading.Thread(target=lambda:asyncore.loop(map=chat_room))
    comm.daemon = True
    comm.start()
    
#    blue = threading.Thread(target=lambda:bluez_notifier(app=app))
#    blue.daemon = True
#    blue.start()

#    espeak = threading.Thread(target=lambda:say.startLoop())
#    espeak.daemon = True
#    espeak.start()

    app.mainloop()
    client.disconnect()

# vim: et:sw=4:ts=4:smarttab:foldmethod=indent:si
