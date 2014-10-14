import logging
import time
import datetime
import re
from multiprocessing import Process, JoinableQueue as Queue
from Queue import Empty
import subprocess
import os.path
import sys
import signal


from flask import Flask

from optparse import OptionParser

EXECWAITTIME = 30



class ProcessTimeOutError(Exception):
    pass

class ProcessInvalidOutputError(Exception):
    pass

class Loggable():

    def _create_logger(self, name, level):

        root = logging.getLogger(name)
        root.setLevel(logging.DEBUG)

        stdout = logging.StreamHandler(sys.stdout)
        stdout.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        stdout.setFormatter(formatter)
        root.addHandler(stdout)

        return root





class Worker(Loggable, Process):

    def __init__(self, span, q_in, q_out, q_status, logger=None):
        super(Worker, self).__init__()

        self.span = span
        self.q_in = q_in
        self.q_out = q_out
        self.q_status = q_status

        q_status.put( str(span) + "- this is it")

        # A flag to notify the proces that it should finish up and exit
        self.terminated = False

        if not logger:
            self.logger = self._create_logger("Worker-{0}".format(span), logging.DEBUG)


    def timeout(self, signum, frame):
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        raise ProcessTimeOutError("Timeout occured.")


    def run(self):
        self.logger.debug('Worker started')
        self.ath(self.span, 5)

        while not self.terminated:
            number = self.q_in.get()
            
            # Terminate execution
            if number is None:
                self.logger.info("Finished on span {1}".format(self.span))
                self.ath(self.span) # send at ATH
                return self.q_in.task_done()

            self.logger.info("Validating {0} on span {1}".format(number, self.span))

            try:
                self.q_out.put(self.stat(self.span, number))
            finally:
                self.ath(self.span, 1)

            self.q_in.task_done()


    def cmd(self, cmd, waittime=30):
        signalset = False

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Install an alarm if there was none installed yet.
        if signal.getsignal(signal.SIGALRM) == signal.SIG_DFL:
            signal.signal(signal.SIGALRM, self.timeout)
            signal.alarm(waittime)
            signalset = True

        try:
            out, err = p.communicate()

            # Reset the alarm.
            if signalset:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, signal.SIG_DFL)

            return re.sub('\s+', ' ', out), err

        except ProcessTimeOutError as e:
            raise
        finally:
            if p.returncode is None:
               p.terminate()
 

    def stat(self, span, number):

        args = ["/usr/sbin/asterisk"]
        args.extend(["-rx gsm check phone stat {0} {1} {2}".format(str(span), number, str(1))])

        try:
            out, err = self.cmd(args, EXECWAITTIME)

            match = re.search(r'PHONE:(#31#)?\+?\d+ (.*)', out)
            if match:
                return number, match.group(2)
            else:
                print out
                raise ProcessInvalidOutputError(out)

        except (ProcessTimeOutError, ProcessInvalidOutputError) as e:
            self.logger.error("{0} occured, sending explicit ATH on span {1}".format(type(e).__name__, str(span)))
            self.ath(span, 5)


    def ath(self, span, waittime=10):
        
        args = ["/usr/sbin/asterisk"]
        args.extend(["-rx gsm send at {0} ATH".format(str(span))])

        try:
            out, err = self.cmd(args, EXECWAITTIME)
        except ProcessTimeOutError as e:
            pass
         
        # Give the PBX time to hangup the active call
        time.sleep(waittime)

        self.logger.info("Succesfully send ATH on span {0}".format(str(span)))
 

class Printer(Loggable, Process):

    def __init__(self, q_out, outfile, logger=None):
        super(Printer, self).__init__()

        self.q_out = q_out
        self.outfile = outfile

        # A flag to notify the proces that it should finish up and exit
        self.terminated = False

        if not logger:
            self.logger = self._create_logger("Printer", logging.DEBUG)


    def run(self):
        self.logger.debug('Printer started')

        with open(self.outfile, 'w', 0) as outfile: # unbuffered
            while not self.terminated:
                try:
                    (number, status) = self.q_out.get(timeout=1)

                    # Terminate execution
                    if (number, status) == (None, None):
                        return self.q_out.task_done()

                    self.logger.info("Got {0} for {1}".format(status, number))

                    # Wrrite output
                    outfile.write(','.join([number, status]) + '\n')
                    
                    # Signal task done
                    self.q_out.task_done()
                except Empty:
                    pass
                except TypeError:
                    pass


#class Frontend:

    #def __init__(self):
        # bind to outqueue
        # launch flask webserver
        # bind 




# run the controller as a seperate process to be able to also run the frontend
#

class Controller(Loggable, Process):

    def __init__(self, arguments, q_in, q_out, q_status):
        super(Controller, self).__init__()

        print "controller initializing"

        (self.options, self.args) = arguments
        options = self.options

        if options.verbose:
            print("Verbose output enabled.")
            print("Number of spans %s" % options.span)

        #if options.tail < 0:
        #    parser.error("Tail must be unsigned")

        #if len(options.head) + len(options.tail) > 15:
        #    print("E.164 numbers cannot be longer then 15 digits")
        #    sys.exit(1)

        if options.outfile is None or os.path.isfile(options.outfile):
            print("Outfile omitted or already exists")
            sys.exit(1)

        if not (os.path.isfile(options.infile) or os.access(options.infile, os.R_OK)):
            print("Infile does not exist or is not readable")
            sys.exit(1)

        if not (os.path.isfile("/usr/sbin/asterisk") or os.access("/usr/sbin/asterisk", os.X_OK)):
            print("Asterisk path does not exist or is not executable")
            sys.exit(1)

        # input queue
        self.q_in = q_in

        # output queue
        self.q_out = q_out

        self.q_status = q_status

        self.children = []
        print "controller initialization complete"

    ##
    # Starts creating worker processes and running the tests
    ##
    def run(self):
        # launches worker process
        for i in range(self.options.span):
            print "creating worker: ", i+1
            worker = Worker(i + 1, self.q_in, self.q_out, self.q_status[i])
            worker.daemon = False
            worker.start()
            self.children.append(worker)
            print self.children

        # launches printer proces
        printer = Printer(self.q_out, self.options.outfile)
        printer.deamon = False
        printer.start()
        self.children.append(printer)

        print self.children

        #tail = abs(int(options.tail))
        #for t in (("{0:0%sd}" % len(str(tail))).format(x) for x in range(tail + 1)):
        #    q_in.put("{0}{1}{2}".format("#31#" if options.private is True else "", options.head, t))

        with open(self.options.infile, 'r') as f:
            for number in f:
                self.q_in.put("{0}{1}".format("#31#" if self.options.private is True else "", number.strip()))

        print "Loaded infile"

        for i in range(self.options.span):
            self.q_in.put(None)  # signal EOF


    

        print "Controller running"
        while len(self.children) > 0:
            print len(self.children)
            try:
                # Join all worker processes using a timeout so it doesn't block
                # Filter out children which have been joined or are None
                self.children = [p for p in self.children if p is not None and p.is_alive()]
                for p in self.children:
                    p.join(timeout=1)

                # Signal Printer thread
                if self.children == [printer]:
                    self.q_out.put((None, None))

            except KeyboardInterrupt:
                print "Ctrl-c received! Sending kill to process..."
                for p in self.children:
                    p.terminate() # PROBLEEM





def main():

    usage = "usage: %prog [options]"
    parser = OptionParser(usage)
    parser.add_option("-s", "--span", type="int", dest="span", help="span")
    parser.add_option("-i", "--in", type="string", dest="infile", help="infile; read a single E.164 numbers per line")
    parser.add_option("-o", "--out", type="string", dest="outfile", help="outfile; csv [E.164],[status]", default="outfile" + datetime.datetime.now().isoformat())   

    # range
    #parser.add_option("-p", "--head", type="string", dest="head", help="head; first n digits")
    #parser.add_option("-t", "--tail", type="string", dest="tail", help="tail; last n digits")
    parser.add_option("-c", "--caller-id", action="store_false", dest="private", help="Show caller-id")
    parser.add_option("-n", "--no-caller-id", action="store_false", dest="private", help="Hide caller-id")
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=True, help="Output verbose [default]")

    #(options, args) = parser.parse_args()
    q_in = Queue(maxsize=0)
    q_out = Queue(maxsize=0)

    (options, args) = parser.parse_args()

    q_status = []

    for i in range(options.span):
        q_status.append(Queue(maxsize=0))

    print q_status

    c = Controller((options, args), q_in, q_out, q_status)
    c.deamon = False
    c.start()

    

    @app.route("/")
    def hello():
        out = str(q_in.get())

        print out
        return out

    @app.route("/rand")
    def rand():
        return str(c.get_children())

    


if __name__ == "__main__":

    app = Flask(__name__)
    main()

    app.run()



