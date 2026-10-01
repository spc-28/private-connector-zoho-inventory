import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PAGE = b"<html><body><p>Zoho authorization received. You can close this tab.</p></body></html>"


def receive_redirect(redirect_uri: str, auth_url: str, timeout_seconds: int = 180) -> dict:
    """Opens the browser for consent and returns the query parameters of the redirect."""
    target = urlparse(redirect_uri)
    received: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path != target.path:
                self.send_response(404)
                self.end_headers()
                return
            received.update({key: values[0] for key, values in parse_qs(url.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *args):
            pass

    server = HTTPServer((target.hostname, target.port), Handler)
    server.timeout = 1
    print(f"Opening the browser for Zoho consent. If it does not open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)
    deadline = time.monotonic() + timeout_seconds
    try:
        while not received and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    return received
