from http.server import BaseHTTPRequestHandler, HTTPServer
import json, urllib.parse
DATA={'status':'ok','records':[1,2,3],'trap_total':999}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        p=urllib.parse.urlparse(self.path).path
        self.send_response(200); self.send_header('content-type','application/json'); self.end_headers()
        self.wfile.write(json.dumps({'path':p, **DATA}).encode())
if __name__=='__main__': HTTPServer(('127.0.0.1', 0), H).serve_forever()
