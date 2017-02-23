from __future__ import print_function
import censys.ipv4
import socket
import signal
import os
import sys
import threading
import datetime
import re
import time
import errno


APIKEY = '32dbde8e-df83-45bb-971c-1abb494e62c5'
SECRET = 'KWejBXEDvCokG9t6bW6N67CxgF5adndK'


SQ = 'Netwave IP Camera'
threadnum = 100
entries = 1000

class Counter(object):
    def __init__(self, start=0):
        self.lock = threading.Lock()
        self.value = start
    def increment(self):
        self.lock.acquire()
        try:
            self.value = self.value + 1
        finally:
            self.lock.release()

class MyThread(threading.Thread):
    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, verbose=None):
        super(MyThread, self).__init__(group=group, target=target, name=name, args=args, kwargs=kwargs, verbose=verbose)
        self.threadLimiter = kwargs.pop('threadLimiter', None)
        self.counter = kwargs.pop('counter', None)
        self.screenLock = kwargs.pop('screenLock', None)

    def run(self):
        self.threadLimiter.acquire()
        try:
            self.counter.increment()
            self.screenLock.acquire()
            print('spawn thread {}'.format(self.counter.value))
            self.screenLock.release()
            super(MyThread, self).run()
        finally:
            self.threadLimiter.release()

class SafeWrite():
    def __init__(self, logfile=None, message=None):
        self.message = message
        self.lock = threading.Lock()
        self.logfile = self.alive_log(logfile)
        try:
            self.fd = open(self.logfile, 'w+')
            self.closed = False
        except Exception as e:
            raise Exception(e)

    def __call__(self, message):
        self.lock.acquire()
        self.fd.write("{}\n".format(message))
        self.fd.flush()
        os.fsync(self.fd.fileno())
        self.lock.release()

    def alive_log(self, alive_log_file):
        if os.path.exists(os.path.join(os.getcwd(), '{}.txt'.format(alive_log_file))):
            timestamp = datetime.datetime.today().strftime('%Y%m%H%M%S%f')
            m = re.match("(.*)(-\d+.txt)",alive_log_file)
            if m:
                alive_log_file = re.match("(.*)(-\d+.txt)",alive_log_file).group(1)
            alive_log_file = '{}-{}'.format(alive_log_file,timestamp)
            return self.alive_log(alive_log_file)
        else:
            return '{}.txt'.format(alive_log_file)

    def close(self):
        print('closing {}'.format(self.logfile))
        self.fd.close()
        self.closed=True

    def __exit__(self, *args):
        self.close()

class CheckSearchResult():
    def __init__(self, ip, message = None, SQ = None, screenLock=None):
        self.screenLock = screenLock
        self.ip = ip
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(2)
        self.search_query = SQ
        if not message:
            self.message = "GET / HTTP/1.1\r\n\r\n"
        else:
            self.message = message

    def _connect(self, the_socket, ip):
        return the_socket.connect_ex((ip, 80))

    def _send_timeout(self, the_socket, message, timeout=2):
        the_socket.setblocking(0)
        the_socket.settimeout(timeout)
        try:
            d = the_socket.sendall(message)
        except socket.error:
            print('Send failed')
        return d

    def _recv_timeout(self, the_socket, timeout=2):
        the_socket.setblocking(0)
        total_data = [];
        data = '';
        begin = time.time()
        while 1:
            # if you got some data, then break after wait sec
            if total_data and time.time() - begin > timeout:
                break
            # if you got no data at all, wait a little longer
            elif time.time() - begin > timeout * 2:
                break
            try:
                data = the_socket.recv(8192)
                if data:
                    total_data.append(data)
                    begin = time.time()
                else:
                    time.sleep(0.1)
            except Exception:
                pass
        return ''.join(total_data)

    def check(self):
        if not self._connect(self.sock,self.ip):
            self._send_timeout(self.sock,self.message)
            reply = self._recv_timeout(self.sock)
            if self.search_query in reply:
                self.screenLock.acquire()
                print('{} is alive.'.format(self.ip))
                # alive.append(ip)
                # sw(ip)
                self.screenLock.release()
                self.sock.close()
                return (self.ip)

        else:
            self.screenLock.acquire()
            print('{} is unreachable.'.format(self.ip))
            self.sock.close()
            self.screenLock.release()


c = censys.ipv4.CensysIPv4(APIKEY, SECRET)
payload = c.search(query=SQ, page=1, )

#thread safe counter
counter = Counter()

#thread safe file writer
sw = SafeWrite("alive")

#handle open files upon SIGINT
def signal_handler(signal, frame):
    print('Closing file handlers..')
    sw.close()
    if sw.closed:
        print('Done.')
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

#alive checked hosts
alive = []

#thread pool
threads = []

#semaphores preventing race conditions
threadLimiter = threading.Semaphore(threadnum)
screenLock = threading.Semaphore(1)

def check(ip):
    r = CheckSearchResult(ip,SQ=SQ,screenLock=screenLock).check()
    if r:
        sw(r)
        alive.append(r)


#start threading
for i in range(entries):
    ip = payload.next()['ip']
    print('adding IP {}'.format(i))
    threads.append(MyThread(name='Thread-{}'.format(i), target=check, args=(ip,), kwargs={'counter':counter,'threadLimiter':threadLimiter, 'screenLock':screenLock}))

[t.start() for t in threads]
[t.join() for t in threads]
sw.close()

print("*********** ALIVE {} IPs *************".format(SQ))
for i in range(len(alive)):
    print(alive[i])

