"""Shared-host (office LAN) settings: who may connect, same-origin checks, the optional HTTPS listener and LAN addresses.

Everything here is driven by the optional "network" section of backend/config.json. With no section, the app accepts
loopback and private (RFC 1918 / link-local / unique-local) addresses only, so it is never usable from the public internet
even if a router port is opened by mistake.
"""
import ipaddress
import os
import re
import socket
import ssl
import sys
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

DEFAULT_NETWORKS = ["127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                    "169.254.0.0/16", "fc00::/7", "fe80::/10"]
CA_FILE = "certs/office-ca.crt"


def settings(config):
    n = config.get("network") or {}
    h = n.get("https") or {}
    nets = []
    for item in n.get("allowed_networks") or DEFAULT_NETWORKS:
        try:
            nets.append(ipaddress.ip_network(str(item).strip(), strict=False))
        except ValueError:
            print("network.allowed_networks: ignoring invalid entry", repr(item))
    try:
        days = max(0.0, float(n.get("session_days", 30)))
    except (TypeError, ValueError):
        days = 30.0
    return {
        "networks": nets,
        "allowed_origins": {str(o).strip().rstrip("/").lower() for o in n.get("allowed_origins") or [] if str(o).strip()},
        "session_days": days,
        "public_url": str(n.get("public_url") or "").strip().rstrip("/"),
        "https": {"enabled": bool(h.get("enabled")), "port": int(h.get("port", 8443)),
                  "cert": h.get("cert") or "certs/server.crt", "key": h.get("key") or "certs/server.key",
                  "redirect_lan_http": bool(h.get("redirect_lan_http"))},
    }


def _ip(value):
    ip = ipaddress.ip_address(str(value).split("%")[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip


def client_allowed(address, net):
    try:
        ip = _ip(address)
    except ValueError:
        return False
    return any(ip.version == n.version and ip in n for n in net["networks"])


def is_loopback(address):
    try:
        return _ip(address).is_loopback
    except ValueError:
        return False


def origin_ok(origin, host, allowed_origins=()):
    """Browsers send Origin on cross-site and same-site POSTs. Allow only this server's own origin (or configured ones)."""
    if not origin:
        return True  # same-origin navigation, curl, urllib: there is no other site involved
    origin = origin.strip().rstrip("/").lower()
    if origin == "null":
        return False
    if origin in allowed_origins:
        return True
    return bool(host) and urlsplit(origin).netloc == host.strip().lower()


_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


def host_only(host_header):
    """Hostname or IPv4 from a Host header, or None if it is not a plain safe value (used to build redirects)."""
    host = (host_header or "").strip().rsplit(":", 1)[0] if (host_header or "").count(":") <= 1 else ""
    return host if host and _HOST.match(host) else None


def lan_ipv4():
    """This PC's IPv4 addresses, best first: the default-route (office LAN) address, then other private LAN
    addresses, then anything else (VPN such as Tailscale 100.x, virtual adapters)."""
    found, primary = set(), None
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            primary = s.getsockname()[0]
            found.add(primary)
    except OSError:
        pass
    def rank(ip):
        a = ipaddress.ip_address(ip)
        return (ip != primary, not (a.is_private and not a in ipaddress.ip_network("100.64.0.0/10")), tuple(int(p) for p in ip.split(".")))
    return sorted((ip for ip in found if not ip.startswith(("127.", "169.254.", "0."))), key=rank)


def tls_context(cert, key):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    return ctx


class TLSServer(ThreadingHTTPServer):
    """HTTPS listener. The TLS handshake runs in the per-connection thread so one slow client cannot block accept()."""
    daemon_threads = True

    def __init__(self, address, handler, context):
        super().__init__(address, handler)
        self.socket = context.wrap_socket(self.socket, server_side=True, do_handshake_on_connect=False)

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ssl.SSLError, ConnectionError, TimeoutError, OSError)):
            return  # untrusted certificate, plain HTTP on the TLS port, closed tab: not server errors
        super().handle_error(request, client_address)


def resolve(root, path):
    return path if os.path.isabs(path) else os.path.join(root, path)
