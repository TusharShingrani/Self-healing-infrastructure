"""Bounded HTTP transports; callers never provide shell strings."""
import http.client,json,socket,urllib.request,urllib.error,ssl
class UnixConnection(http.client.HTTPConnection):
    def __init__(self,path):super().__init__('localhost',timeout=6);self.path=path
    def connect(self):self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(self.timeout);self.sock.connect(self.path)
class UnixClient:
    def __init__(self,path):self.path=path
    def request(self,path,data=None):
        c=UnixConnection(self.path)
        try:
            c.request('GET' if data is None else 'POST',path,body=None if data is None else json.dumps(data),headers={'Content-Type':'application/json'});r=c.getresponse();raw=r.read(65537)
            if len(raw)>65536:raise RuntimeError('Broker response exceeds bound')
            result=json.loads(raw)
            if r.status!=200:raise RuntimeError(result.get('error','Broker refused request'))
            return result
        finally:c.close()
class RemoteClient:
    def __init__(self,url,allow_plaintext_lab=False):
        if not url.startswith('https://') and not (allow_plaintext_lab and url.startswith('http://')):raise ValueError('Verified HTTPS required outside explicit private lab overlay')
        self.url=url.rstrip('/')
    def request(self,path,data=None):
        request=urllib.request.Request(self.url+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=6) as response:raw=response.read(65537)
        except urllib.error.HTTPError as exc:raise RuntimeError('Agent refused request') from exc
        if len(raw)>65536:raise RuntimeError('Agent response exceeds bound')
        return json.loads(raw)
