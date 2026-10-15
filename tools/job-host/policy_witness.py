"""Independent in-namespace positive/negative network checks, without credentials."""
import json,socket,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
LATEST={'database_network_allowed':None,'monitor_network_denied':None,'time':0}

def reaches(host,port):
    try:
        with socket.create_connection((host,port),timeout=2):return True
    except OSError:return False

def loop():
    global LATEST
    while True:
        LATEST={'database_network_allowed':reaches('10.1.1.83',5432),'monitor_network_denied':not reaches('10.1.1.50',9090),'time':time.time()}
        time.sleep(5)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!='/status':self.send_error(404);return
        body=json.dumps(LATEST).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

if __name__=='__main__':
    threading.Thread(target=loop,daemon=True).start();ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
