import SimpleHTTPServer
import SocketServer
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
from time import sleep
from os import curdir, sep
import random
from Queue import Queue
import sys


PORT = 8080

Handler = SimpleHTTPServer.SimpleHTTPRequestHandler




# Handler 
class dailerHandler(BaseHTTPRequestHandler):

	def __init__(self):
		print "Initializing dailerHandler"

	
	def do_GET(self):
		self.send_response(200)

		if self.path.endswith(".css"):
			self.send_header('Content-type','text/css')
		else:
			self.send_header('Content-type','text/html')
		self.end_headers()

		if (self.path == "/ajax"):
			self.wfile.write(random.randint(1,100))
		elif self.path == "/":
			self.wfile.write(open("htdocs/index.htm").read())
		elif self.path == "/form":
			self.wfile.write(open("htdocs/form.html").read())
		elif self.path == "/dailer":
			self.wfile.write(open("htdocs/dailer.html").read())	
		elif self.path == "/style.css":
			self.wfile.write(open("htdocs/style.css").read())
		else:
			self.wfile.write(open(curdir+sep+self.path).read())
		return


	# Return square root
	def do_POST(self):
		length = int(self.headers.getheader('content-length'))
		data_string = self.rfile.read(length)
		try:
			result = int(data_string) ** 2
		except:
			result = "error"

		self.wfile.write(result)


class WriteableQueue:

	def __init__(self):
		self.content = Queue()

	def write(self,string):
		if string != "\n":
			self.content.put(string)

	def read(self):
		if self.content.qsize():
			return self.content.get_nowait()
		else:
			return None


#httpd = SocketServer.TCPServer(("",PORT), dailerHandler)

outQueue = WriteableQueue()

sys.stdout = outQueue

print 123
print 456
print 789


sys.stdout = sys.__stdout__
print outQueue.content.qsize()

print outQueue.read()
print outQueue.read()
print outQueue.read()
print outQueue.read()

#print "content: ", outQueue.read()
#print outQueue.content.get()

try:
	httpd=HTTPServer(('',PORT), dailerHandler)

	print 'Started server on port', PORT
	

	httpd.serve_forever()

except:
	print '^C received, shutting down'
	httpd.socket.close()


