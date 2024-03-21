#!/usr/bin/python3

import asynchat
import asyncore
import socket
import threading
import time
import optparse
import sys
from time import sleep
import struct
import re
import logging
import logging.handlers
import datetime
import os
import math
 
class ChatClient(asynchat.async_chat):
 
    def __init__(self, sockfile, app):
        asynchat.async_chat.__init__(self)
        self.create_socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connect(sockfile)
 
        self.set_terminator(b'\n')
        self.buffer = []
        self.app = app
 
    def collect_incoming_data(self, data):
        self.buffer.append(bytes.decode(data))
        pass
 
    def found_terminator(self):
        msg = ''.join(self.buffer)
        self.buffer = []
        if "Diagnostic" in msg:
            print(msg)
            self.app.kwpenable = True if 'off' in msg else False
        else:
            print("Unknown message: "+msg)
            pass

class sink():
    def __init__(self):
        pass
    
    def push(self, msg):
        pass

def clientThread(r, sockfile): 
    while True:
        try:
            r.connection = ChatClient(sockfile, r)
            print(r)
            print("connect!")
            asyncore.loop()
            print("disconnect!")
        except:
            r.connection = sink()
            time.sleep(0.1)
            pass

# CAN frame packing/unpacking (see `struct can_frame` in <linux/can.h>)
can_frame_fmt = "=IB3x8s"

def dissect_can_frame(frame):
        can_id, can_dlc, data = struct.unpack(can_frame_fmt, frame)
        return (can_id, can_dlc, data[:can_dlc])

 
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

class Redirector:
    def __init__(self, socketCAN, client, spy=False):
        self.SCan = socketCAN
        self.connection = client
        self.spy = spy
        self._write_lock = threading.Lock()
        self.power = 0
        self.sendpoweron = 0
        self.sendpoweroff = 0
        self.tempspy = 0
        self.clickcount = 0
        self.clickflag = False 
        self.activated = True 
        self.modenotset = True 
        self.activetime = 0 
        self.time = 0 
        self.last_steering_key = [0xC0,0x00]
        self.AI=-1
        self.lastpos = -1
        self.d1B8 = [0x0F,0xC0,0xF6,0xFF,0x60,0x21]
        self.aux = True #changed for CCC out...
        self.torque = 0
        self.power = 0
        self.torquecnt = 0
        self.consumecnt = 0
        self.consumed = 0
        self.consumption = 0.0
        self.speed = 0
        self.status = {
            "Power":"Off",
            "Running":"Off",
            "Volts":" 0.00",
        }
        self.kwplist = []
        self.kwpdata = []
        self.kwpsource = -1
        self.kwpenable = True
        self.canlist={}
        for n in dir(self):
            if n[0:3] == 'can':
                func = getattr(self, n)
                if callable(func):
                    can_id = int(n[3:],16)
                    self.canlist[can_id]=func
        print(self.canlist)

    def shortcut(self):
        """connect the serial port to the TCP port by copying everything
           from one side to the other"""
        self.alive = True
        self.thread_read = threading.Thread(target=self.reader)
        self.thread_read.setDaemon(True)
        self.thread_read.setName('serial->socket')
        self.thread_read.start()
        self.writer()

    def _readline(self):
        eol = b'\r'
        leneol = len(eol)
        line = bytearray()
        while True:
            c = self.serial.read(1)
            if c:
                line += c
                if line[-leneol:] == eol:
                    break
            else:
                break
        return bytes(line)

    def _sendkey(self, key):
        if self.connection is not None:
        #try:
            self.connection.push(("000000037ff07bfe 00 "+key+" lcdd\n").encode())
            self.connection.push(("000000037ff07bfe 01 "+key+" lcdd\n").encode())
        #except:
        #    pass

    def send(self, msg):
        self.connection.push((msg+'\n').encode())

    def write(self, msg, data=[]):
        
        if isinstance(msg, str):
            can_id = int(msg[1:4],16)
            can_dlc = int(msg[4])
            data = [(int(msg[n*2+5:n*2+7],16) if n < can_dlc else 0) for n in range(8)]
        elif isinstance(msg, int):
            can_id = msg
            can_dlc = len(data)
            data = [(data[n] if n < can_dlc else 0) for n in range(8)]
        else:
            print('Error!!!')
            print(msg)
            print(data)
            pass

        can_frame_fmt2 = "=IB3x8B"
        self.SCan.send(struct.pack(can_frame_fmt2, can_id, can_dlc, *data)) 

    def kwp2000(self):
        if len(self.kwpdata) < 3:
            return
        
        response = self.kwpdata[1]

        if response == 0x7F:
            #print("[kwp2000] Error response")
            return

        SID = self.kwpdata[1] & 0xCF
        
        request = self.kwpdata[2]<<8 | self.kwpdata[3]
        
        #print("[kwp2000] response: 0x%02X"%response, "SID: 0x%02X"%SID, "Request: 0x%04X"%request, "Source: 0x%02X"%self.kwpsource, "Length: 0x%02X"%len(self.kwpdata))
        self.sendkwp2000()

        if self.kwpsource == 0xA0:
            if request == 0xF202:
                if self.kwpdata[5] == 0x03:
                    self.send('Aux: On')
                    #self.status['Aux'] = 'On'
                    self.aux = True
                else:
                    self.send('Aux: Off')
                    #self.status['Aux'] = 'Off'
                    self.aux = False
            elif request == 0xF301:
                print("Application: "+''.join((chr(x) for x in self.kwpdata[4:])).strip())
            elif request == 0xF124:
                #print(''.join((('0x%02X '%x) for x in self.kwpdata[4:])))
                speed = (self.kwpdata[18] << 8) | self.kwpdata[19]
                #print("Sat speed: %5.1f"%(float(speed)*0.036))
                self.send('SatSpeed: % 5.1f'%(float(speed)*0.036))

    def kwp2000TL(self, can_id, data):
        target = data[0]
        source = can_id & 0x00FF
        if target != 0xF3:
            return

        kwlen = data[1]
        if kwlen & 0xF0 == 0x00: #single frame reply
            self.kwpdata = data[1:(2+kwlen)]
            self.kwpsource = source
            self.kwp2000()
            self.kwpdata = []
        elif kwlen & 0xF0 == 0x10: #first frame
            self.kwpdata = data[2:]
            self.kwpsource = source
            data = [source, 0x30, 0x0F, 0x02] +[0xFF]*4
            self.write(0x6F3, data)

        elif kwlen & 0xF0 == 0x20: #Continuation frame
            if self.kwpsource == source:
                self.kwpdata += data[2:]
                if len(self.kwpdata)>=self.kwpdata[0]: #check if we got all data
                    self.kwpdata = self.kwpdata[0:self.kwpdata[0]]
                    self.kwp2000()
            else:
                self.kwpdata = []
                self.kwpsource = -1

    def sendkwp2000(self):
        #address A0, 03 bytes, cmd 22 (ReadDataByCommonIdentifier), ID F202
        if not self.kwpenable:
            return
        if len(self.kwplist)==0:
            return
        
        request = self.kwplist.pop(0)
        data = request['data']
        datalen = len(data)
        if datalen > 6:
            #TODO: fill out data so it has lenght 5+n*6
            data += [0xFF]*(6-int((datalen-5)%6))
            #first frame
            msgdata = [
                request['target'], 
                (0x10 | (datalen >> 8)),
                datalen&0xFF] + data[0:5]
            self.write(0x6F3, data)
            for n in range(int((data-5)//6)):
                msgdata = [
                    request['target'], 
                    (0x20 | (n&0x0f))] + data[5+n*6:11+n*6]
                self.write(0x6F3, data)
        else:
            data = [request['target'], datalen] + data + [0xFF]*(6-datalen)
            self.write(0x6F3, data)
        
    
    def can2F8(self, data): 
        #Use this id to get system time
        try:
            date = datetime.datetime(
                year=data[6]*256+data[5], 
                month=data[4]>>4, 
                day=data[3], 
                hour=data[0], 
                minute=data[1], 
                second=data[2])
            td = datetime.datetime.now() - date
            if abs(td.total_seconds()) > 600:
                os.system('date -s "%s"'%date.ctime())
        except:
            pass

    def can3B4(self, data):
        volts = float(((data[1]&0x0F)<<8)+data[0]) / 68.0
        self.send('Volts: %2.02f'%volts)
    
    def can1D0(self, data):
        temp = float(data[0])-48.0
        self.send('ETemp: %2.01f'%temp)
        consumption = float(data[5]*256)+float(data[4])
        if (self.consumed - consumption)>32676:
            self.consumed -= 65536
            self.consumption -= 65536.0
        self.consumecnt += 1
        #print(consumption)
        if self.consumecnt == 5:
            if self.speed>3:
                self.send('Consume: '+'%3.01f'%((consumption-self.consumed)/(self.consumecnt*100.0)*3600.0/self.speed))
            else:
                self.send('Consume: -.--')
            self.consumed = consumption
            self.consumecnt = 0
            self.send('Consumption: %3.0f'%((consumption - self.consumption)/(1000.0)))

    def can32E(self, data):
        temp = float(data[3])/10.0 + 6
        self.send('ITemp: %2.01f'%temp)

    def can0AA(self, data):
        torque = float(data[2])*256+float(data[1]&0xF0)
        if int(data[2])>127:
            torque -= 65536.0
        torque /= 32.0
        rpm = (float(data[5])*256+float(data[4]))/4.0
        self.torque += torque
        self.power += (torque*rpm*2*math.pi/60.0/1000.0)
        self.torquecnt += 1
        if self.torquecnt == 5:
            self.send('Torque: '+'%3.01f'%(self.torque/self.torquecnt))
            self.send('EnginePwr: '+'%3.0f'%(self.power/self.torquecnt))
            self.torque = 0
            self.power = 0
            self.torquecnt = 0
        if self.status['Running'] == 'Off' and rpm>500:
            print('Car started!')
            self.status['Running'] = 'On'
            senddata = [0x44, 0x06, 0x31, 0xFC, 0x02, 0x01, 0x0C, 0x0A]
            self.write(0x6F3, senddata)
        if self.status['Running'] == 'On' and rpm<100:
            print('Car stopped!')
            self.status['Running'] = 'Off'
            senddata = [0x44, 0x06, 0x31, 0xFC, 0x02, 0x01, 0x01, 0xF4]
            self.write(0x6F3, senddata)

    def can1A0(self, data):
        self.speed = (float(data[1]&0x0F)*256+float(data[0]))*.1
        #print('speed: %f'%self.speed)

    def can328(self, data):
        #sys.stdout.write("ID: "+ID+"l: "+l+" | "+d[:-1]+"\n")
        #self.time = int(d[4:6]+d[2:4]+d[0:2],16)
        self.time = data[2]<<16 + data[1]<<8 + data[0]

        #request mixer status through KWP.
        self.kwplist = [
            {'target':0xA0, 'data':[0x22, 0xF2, 0x02]},
            {'target':0xA0, 'data':[0x22, 0xF1, 0x24]},
            #{'target':0xA0, 'data':[0x22, 0xF3, 0x01]}, #program name
        ]
        self.sendkwp2000()
        #print('\n'.join([key+': '+str(value) for key,value in self.status.items()])+'\n')
        #print(self.connection)
        
        #Send status data to the clients
        #self.send('\n'.join([key+': '+str(value) for key,value in self.status.items()]))
        #Make sure the screen is in the right mode
        if self.activated:
            self.write('t21e76A01010A010101')
        else:
            self.write('t21e76501010A010101')

        if self.modenotset:
            self.write("t1AA8"+self.klicker+"\r")
            self.modenotset = False
    
    def can130(self, data):
        #sys.stdout.write("ID: "+ID+"l: "+l+" | "+d[:-1]+"\n")
        if self.status['Power'] == 'Off' and not data[0]&0xF0 == 0x00:
            self.status['Power'] = 'On' 
            #Just turned on
            self.consumption = 0.0
            self.write("t1AA8"+self.klicker+"\r")

        if self.status['Power'] == 'On' and data[0]&0xF0 == 0x00:
            self.status['Power'] = 'Off' 
            #Just turned off
        
        self.send('Power: %s'%self.status['Power'])

    def can228(self, data):
        #sys.stdout.write("ID: "+ID+"l: "+l+" | "+d[:-1]+"\n")
        #if d[1] == '0':
        if data[0]&0x0f == 0x00:
            pass
        #elif d[1] == 'C':
        elif data[0]&0x0f == 0x0C:
            self.activated = not self.activated
            if self.activated:
                self.write('t21e76A01010A010101')
                self.activetime = self.time
                #self.write("t1AA8F36E140110002070\r")
                self.write("t1AA8F000000000000000\r")
                sleep(0.1)
                self.write("t1AA8"+self.klicker+"\r")
                self.lastpos = -100000
            else:
                self.write('t21e76501010A010101')
                #self.write("t1AA8F36E140110002070\r")
                self.write("t1AA8F000000000000000\r")
                sleep(0.1)
                self.write("t1AA8F36E140100002080\r")

            sys.stdout.write("press-->"+("Active!" if self.activated else "Inactive!")+"\n")
            

    def can1D6(self, data):
        #if d[0]=='C' and self.aux:
        if data[0] == 0xC0 and self.aux:
            if self.last_steering_key[0]&0xF0 == 0xE0:
                sys.stdout.write("UP from wheel\n")
                self.send("UP")
            elif self.last_steering_key[0]&0xF0 == 0xD0:
                sys.stdout.write("DOWN from wheel\n")
                self.send("DOWN")
            elif self.last_steering_key[0] == 0xC4:
                sys.stdout.write("VolDOWN from wheel\n")
                self.send("VOLDOWN")
            elif self.last_steering_key[0] == 0xC8:
                sys.stdout.write("VolUP from wheel\n")
                self.send("VOLUP")
        #if d[2]=='1':
        #    self.tempspy = 500
        
        self.last_steering_key = data
        #sys.stdout.write("ID: "+ID+"l: "+l+" | "+d[:-1]+"\n")
        
    def can1B8(self, data):
        #sys.stdout.write("ID: "+ID+"l: "+l+"|"+d[:-1]+"|"+str(self.clickcount)+"\n")
        #if d[3] == '0':
        if data[1]&0x0F == 0x00:
            #store for later use in sending home key to CCC
            self.d1B8 = data

        #if self.activated:
        #    #still doing something... update watchdog time
        #    self.activetime = self.time

        #if d[3] == '1' and self.activated:
        if data[1]&0x0F == 0x01 and self.activated:
            self.clickflag = True
        #if d[3] == '0' and self.activated:
        if data[1]&0x0F == 0x00 and self.activated:
            if self.clickflag:
                # send Home key
                # or not...
                homekey = list(data)
                homekey[1] = data[1]&0xF0 | 0x04
                self.write(0x1B8, homekey)
                sleep(0.05)
                self.write(0x1B8, data)
                sleep(0.05)
                self.write("t1AA8"+self.klicker+"\r")
                self.lastpos = -100000
                
                self.clickflag = False
                sys.stdout.write("CLICK\n")
                self.send("CLICK")

            if self.clickcount > 0 and self.clickcount < 8:
                sys.stdout.write("MENU\n")
                self.send("MENU")
            
            #position = int(d[4:6],16)/256.0+int(d[6:8],16)*1.0
            position = data[2]/256.0+data[3]*1.0
            if position > 128.0:
                position -= 256.0
            position *= 1.6 #maybe this needs to improve...
            sys.stdout.write("%+7.02f -- %+7.02f\n" % (position, self.lastpos))
            delta = position - self.lastpos
            while abs(delta)>0.5:
                if abs(delta)>5: #needs fixing...
                    self.lastpos = round(position)
                elif delta < -0.5:
                    sys.stdout.write("UP\n")
                    self.send("UP")
                    self.lastpos -= 1.0
                elif delta > 0.5:
                    sys.stdout.write("DOWN\n")
                    self.lastpos += 1.0
                    self.send("DOWN")
                delta = position - self.lastpos

        #if d[3] == '4':
        if data[1]&0x0F == 0x04:
            self.clickcount += 1
            if self.clickcount == 8:
                self.activated = not self.activated
                if self.activated:
                    self.write('t21e76A01010A010101')
                    self.activetime = self.time
                #   self.write("t1AA8F36E140110002070\r")
                    self.write("t1AA8F000000000000000\r")
                    sleep(0.1)
                    self.write("t1AA8"+self.klicker+"\r")
                    self.lastpos = -100000
                else:
                    self.write('t21e76501010A010101')
                #   self.write("t1AA8F36E140110002070\r")
                    self.write("t1AA8F000000000000000\r")
                    sleep(0.1)
                    self.write("t1AA8F36E140100002080\r")

                #sys.stdout.write("press-->"+("Active!" if self.activated else "Inactive!")+"\n")
                #self.activated = not self.activated
                #if self.activated:
                #    self.activetime = self.time
                #    self.write("t1AA8F36E140110002070\r")
                #    #self.write("t1AA8F000000000000000\r")
                #    sleep(0.1)
                #    self.write("t1AA8"+self.klicker+"\r")
                #    self.lastpos = -100000
                #else:
                #    self.write("t1AA8F36E140110002070\r")
                #    #self.write("t1AA8F000000000000000\r")
                #    sleep(0.1)
                #    self.write("t1AA8F36E140100002080\r")

                sys.stdout.write("longpress-->"+("Active!" if self.activated else "Inactive!")+"\n")
            if self.clickcount == 70:
                os.system("reboot")
        else:
            self.clickcount = 0


    def can1AA(self, data):
        #sys.stdout.write("ID: "+ID+"l: "+l+"|"+d+"\n")
        if self.activated:
            if (list(data) == [0xF3,0x6E,0x14,0x06,0x00,0x00,0x20,0x80] or
                    list(data) == [0xF3,0x6E,0x14,0x06,0x05,0x00,0x20,0x80]):
                homekey = list(self.d1B8)
                homekey[1] = self.d1B8[1]&0xF0 | 0x04
                self.write(0x1B8, homekey)
                sleep(0.05)
                self.write(0x1B8, self.d1B8)
                self.lastpos = -100000
            elif list(data) == [0xF3,0x6E,0x14,0x01,0x00,0x00,0x20,0x80]:
                self.write("t1AA8F000000000000000\r")
                sleep(0.01)
                self.write("t1AA8"+self.klicker+"\r")
                self.lastpos = -100000
            else:
                #self.write("t1AA8"+self.klicker+"\r")
                #self.lastpos = -100000
                print("CAN ID 1AA: ",('0x%02X,'*len(data))%tuple(data))

            #sleep(0.1)
            #self.write('t1B86'+self.d1B8[0:3]+'4'+self.d1B8[4:])
            #sleep(0.1)
            #self.write('t1B86'+self.d1B8)
            #sleep(0.1)
            #self.write("t1AA8F000000000000000\r")
            #sleep(0.1)
            #self.write("t1AA8"+self.klicker+"\r")
            #self.lastpos = -100000

                                                   #F36E140100002080
    def reader(self):
        """loop forever and copy serial->socket"""
        self.klicker = "F363204020002020"
        self.klicker = "F313108040002020"
        self.klicker = "F1570A8014002010"
        self.clickcount = 0
        self.lastpos = -1
        self.receivelist = []
        
        sys.stdout.write("Starting to read the serial CANBUS input\n")

        while True:
            try:
                cf, addr = self.SCan.recvfrom(16)
         
                can_id, can_dlc, data = dissect_can_frame(cf)
                #print('Received: can_id=%x, can_dlc=%x, data=%s' % dissect_can_frame(cf))

                
                if True:
                    ID = '%03X' % can_id
                    l = '%X' % can_dlc
                    d = str.join("",[('%02X' % d) for d in data])+'\r'
                    #sys.stdout.write("ID: "+ID+"l: "+l+" | "+d[:-1]+"\n")

                    if ID not in self.receivelist:
                        self.receivelist.append(ID)
                        #sys.stdout.write("first time for ID: "+ID+"l: "+l+" | "+d[:-1]+"\n")
                    if (can_id & 0xF00) == 0x600:
                        #sys.stdout.write("diag: "+ID+": "+l+" | "+d[:-1]+"\n")
                        try:
                            self.kwp2000TL(can_id, data)
                        except:
                            #seems to go wrong sometimes with bad data...
                            pass
                    
                    if can_id in self.canlist:
                        self.canlist[can_id](data)

                if self.tempspy>0:
                    sys.stdout.write(data+"\n")
                    self.tempspy-=1
        
                if self.spy:
                    sys.stdout.write(data+"\n")
        
                sys.stdout.flush()
            except (socket.error):
                sys.stderr.write('ERROR in the CAN socket code somewhere...\n')
                # probably got disconnected
                break
                self.alive = False
            except:
                raise
            
    def stop(self):
        """Stop copying"""
        if self.alive:
            self.alive = False
            self.thread_read.join()

if __name__ == '__main__':
 
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

    parser.add_option("--spy",
        dest = "spy",
        action = "store_true",
        help = "peek at the communication and print all data to the console",
        default = False
    )
    
    parser.add_option("-s", "--socket",
        dest = "socket",
        help = "Socket to create for communication with can app",
        default = "/var/run/sockfile",
        )
    
    (options, args) = parser.parse_args()
    
    # create a raw socket and bind it to the given CAN interface
    s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    s.bind(("can0",))

    if options.quiet:
        stdout_logger = logging.getLogger('log')
        stdout_logger.setLevel(logging.DEBUG)
        handler = logging.handlers.RotatingFileHandler(
              '/tmp/can.log', maxBytes=1e6, backupCount=5)
        formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s:%(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        stdout_logger.addHandler(handler)
        sl = StreamToLogger(stdout_logger, logging.INFO)
        sys.stdout = sl
        sys.stderr = sl

    sys.stderr.write("--- Serial panasonic control from MusicPD --- type Ctrl-C / BREAK to quit\n")
    
    r = Redirector(
            s,
            sink(),
            options.spy,
            )

    comm = threading.Thread(target=lambda:clientThread(r, options.socket))
    comm.daemon = True
    comm.start()

    try: 
        while True:
            try:
                r.reader()
                if options.spy: sys.stdout.write('\n')
                sys.stderr.write('Disconnected\n')
                #connection.close()
            except KeyboardInterrupt:
                break
            except (socket.error):
                sys.stderr.write('ERROR\n')
                sleep(1)
                #msg = input('> ')
                #msg = 'UP'    
                #time.sleep(5)
                #client.push((msg + '\n').encode())
                #client.push(b'dit is een lang verhaal\nmet terminators erin\nUP\nhoe gaat het ding hiermee om?\n')
    finally:
        pass
       
# vim: et:sw=4:ts=4:smarttab:foldmethod=indent:si
