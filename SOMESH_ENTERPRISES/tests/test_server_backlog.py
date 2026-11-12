"""A page load opens ~30 connections at once. They must queue while the server is busy, never be refused.

Regression: with Python's default listen backlog (5), Windows refused the overflow (net::ERR_CONNECTION_REFUSED for
utils.js and other scripts), and the reloaded page failed with "syncClock is not defined".
"""
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler

from support import AppFixture, BACKEND

sys.path.insert(0, str(BACKEND))
import lan as LAN  # noqa: E402

BURST = 40


class Ok(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        body = b'ok'
        self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)


def burst(server_class, count=BURST):
    """Connect BURST clients while accept() is not running (a busy server), then serve. Returns refused, answered."""
    quiet = type('Quiet', (server_class,), {'handle_error': lambda self, *a: None})  # refused/reset sockets are expected here
    srv = quiet(('127.0.0.1', 0), Ok)
    port = srv.server_address[1]; socks = []; refused = 0
    try:
        for _ in range(count):
            s = socket.socket(); s.settimeout(2)
            try:
                s.connect(('127.0.0.1', port)); s.sendall(b'GET / HTTP/1.0\r\n\r\n'); socks.append(s)
            except OSError:
                refused += 1; s.close()
        threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': .02}, daemon=True).start()
        answered = 0
        for s in socks:
            try:
                answered += s.recv(64).startswith(b'HTTP/1.0 200')
            except OSError:
                pass
            finally:
                s.close()
        return refused, answered
    finally:
        srv.shutdown(); srv.server_close()


class ListenBacklog(unittest.TestCase):
    def test_app_and_https_servers_use_the_large_backlog(self):
        app = AppFixture()
        try:
            self.assertIs(app.g['ThreadingHTTPServer'], LAN.OfficeHTTPServer)
            self.assertIsInstance(app.server, LAN.OfficeHTTPServer)
        finally:
            app.close()
        self.assertGreaterEqual(LAN.OfficeHTTPServer.request_queue_size, 64)
        self.assertTrue(issubclass(LAN.TLSServer, LAN.OfficeHTTPServer))

    def test_a_burst_of_page_load_connections_is_queued_not_refused(self):
        refused, answered = burst(LAN.OfficeHTTPServer)
        self.assertEqual((refused, answered), (0, BURST))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows refuses connections beyond the backlog immediately')
    def test_the_old_default_backlog_refused_connections(self):
        from http.server import ThreadingHTTPServer
        refused, answered = burst(ThreadingHTTPServer, count=8)  # just above the old backlog of 5
        self.assertGreater(refused, 0, 'documents the original failure: the default backlog of 5 overflows')


if __name__ == '__main__':
    unittest.main()
