"""Verified, mutually authenticated TLS; no certificate-validation bypass."""
import ssl
from http.server import HTTPServer
from pathlib import Path


def client_context(directory):
    root=Path(directory)
    context=ssl.create_default_context(cafile=str(root/'ca.crt'))
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(root/'client.crt'),str(root/'client.key'))
    return context


class MutualHTTPServer(HTTPServer):
    def __init__(self,address,handler,directory):
        root=Path(directory);self.context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.minimum_version=ssl.TLSVersion.TLSv1_2
        self.context.load_cert_chain(str(root/'server.crt'),str(root/'server.key'))
        self.context.load_verify_locations(cafile=str(root/'ca.crt'))
        self.context.verify_mode=ssl.CERT_REQUIRED
        super().__init__(address,handler)
    def get_request(self):
        stream,address=self.socket.accept();stream.settimeout(2)
        try:return self.context.wrap_socket(stream,server_side=True),address
        except (ssl.SSLError,OSError):stream.close();raise


def peer_name(connection):
    certificate=connection.getpeercert()
    return next((value for section in certificate.get('subject',()) for key,value in section if key=='commonName'),'')
