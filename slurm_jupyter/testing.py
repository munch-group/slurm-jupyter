

import signal

# class GracefulInterruptHandler(object):

#     def __init__(self, sig=signal.SIGINT):
#         self.sig = sig

#     def __enter__(self):

#         self.interrupted = False
#         self.released = False

#         self.original_handler = signal.getsignal(self.sig)

#         def handler(signum, frame):

#             # answer = input("really: ")
#             # if answer == 'y':
#             #     raise KeyboardInterrupt

#             self.release()
#             self.interrupted = True

#         signal.signal(self.sig, handler)

#         return self

#     def __exit__(self, type, value, tb):
#         self.release()

#     def release(self):

#         if self.released:
#             return False

#         signal.signal(self.sig, self.original_handler)

#         self.released = True

#         return True


class GracefulInterruptHandler(object):

    def __init__(self, sig=signal.SIGINT):
        self.sig = sig

    def __enter__(self):
        self.released = False
        self.original_handler = signal.getsignal(self.sig)

        def handler(signum, frame):
            # answer = input("really: ")
            # if answer == 'y':
            #     raise KeyboardInterrupt
            msg = '\nAre you sure? y/n: '
            try:
                if input(msg) == 'y':
                    raise KeyboardInterrupt
            except RuntimeError: # in case user does Ctrl-C instead of y
                raise KeyboardInterrupt                

        signal.signal(self.sig, handler)
        return self

    def __exit__(self, type, value, tb):
        self.release()

    def release(self):
        if self.released:
            return False
        signal.signal(self.sig, self.original_handler)
        self.released = True
        return True


# import time
# with GracefulInterruptHandler() as h:
#     for i in range(1000):
#         print("...")
#         time.sleep(1)

def kbintr_handler(signal, frame):
    """Intercepts KeyboardInterrupt and asks for confirmation.
    """
    msg = '\nAre you sure? y/n: '
    try:
        if input(msg) == 'y':
            raise KeyboardInterrupt
    except RuntimeError: # in case user does Ctrl-C instead of y
        raise KeyboardInterrupt


def kbintr_repressor(signal, frame):
    """For ignoring KeyboardInterrupt.
    """
    pass
 

from subprocess import Popen, PIPE
def open_port():

    cmd = 'ssh -L6359:s05n24.genomedk.net:6359 kmt@login.genome.au.dk'
    port_p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE)

signal.signal(signal.SIGINT, kbintr_handler)

import time
try:
    port_p, port_t, port_q = open_port()

    for i in range(1000):
        print("...")
        time.sleep(1)
except KeyboardInterrupt:

    signal.signal(signal.SIGINT, kbintr_repressor)

    for i in range(5):
        print("cleaning up")
        time.sleep(1)


# with GracefulInterruptHandler() as h1:
#     while True:
#         print "(1)..."
#         time.sleep(1)
#         with GracefulInterruptHandler() as h2:
#             while True:
#                 print "\t(2)..."
#                 time.sleep(1)
#                 if h2.interrupted:
#                     print "\t(2) interrupted!"
#                     time.sleep(2)
#                     break
#         if h1.interrupted:
#             print "(1) interrupted!"
#             time.sleep(2)
#             break        