"""Create the private office certificate authority and an HTTPS certificate for this Admin PC.

    python tools/make_office_cert.py                 (names and LAN IPs are detected)
    python tools/make_office_cert.py --host 192.168.1.20 --host somesh-admin
    python tools/make_office_cert.py --enable        also switch on HTTPS in backend/config.json (app must be stopped)

Writes into certs/ (excluded from Git):
  office-ca.crt   public CA certificate: install it once on each employee PC (also served at /office-ca.crt)
  office-ca.key   CA private key: never copy it off this PC. Re-running reuses it, so employee PCs do not need a new CA
  server.crt/.key HTTPS certificate for this PC's names and IP addresses (re-run after the IP address changes)
  employee-pc-kit\\ office-ca.crt, the employee launcher and the server address, to copy to each employee PC

Needs the 'cryptography' package on the Admin PC only:  python -m pip install --user cryptography
"""
import argparse
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import lan as LAN  # noqa: E402

CA_NAME = 'SOMESH ENTERPRISES Office CA'
CLIENT_BAT = 'OPEN SOMESH ENTERPRISES (Employee PC).bat'


def _crypto():
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError:
        sys.exit("The 'cryptography' package is needed on this Admin PC:  python -m pip install --user cryptography")
    return x509, hashes, serialization, ec, ExtendedKeyUsageOID, NameOID


def _private(path):
    """Best effort: only the current Windows user may read a private key."""
    if os.name == 'nt':
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f"{os.environ.get('USERNAME', '')}:F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        os.chmod(path, 0o600)


def make(certs, hosts, days=825):
    x509, hashes, serialization, ec, EKU, NameOID = _crypto()
    certs = Path(certs)
    certs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc) - timedelta(minutes=5)
    ca_crt, ca_key = certs / 'office-ca.crt', certs / 'office-ca.key'
    pem = serialization.Encoding.PEM
    if ca_crt.is_file() and ca_key.is_file():
        ca = x509.load_pem_x509_certificate(ca_crt.read_bytes())
        ca_private = serialization.load_pem_private_key(ca_key.read_bytes(), None)
        created_ca = False
    else:
        ca_private = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, CA_NAME), x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'SOMESH ENTERPRISES')])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_private.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                           key_encipherment=False, data_encipherment=False, key_agreement=False,
                                           encipher_only=False, decipher_only=False), critical=True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_private.public_key()), critical=False)
              .sign(ca_private, hashes.SHA256()))
        ca_key.write_bytes(ca_private.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        _private(ca_key)
        ca_crt.write_bytes(ca.public_bytes(pem))
        created_ca = True
    sans, seen = [], set()
    for h in hosts:
        h = h.strip()
        if not h or h.lower() in seen:
            continue
        seen.add(h.lower())
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            sans.append(x509.DNSName(h))
    key = ec.generate_private_key(ec.SECP256R1())
    first = next((h for h in hosts if h), 'localhost')
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, first[:64])]))
            .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([EKU.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_private.public_key()), critical=False)
            .sign(ca_private, hashes.SHA256()))
    (certs / 'server.key').write_bytes(key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    _private(certs / 'server.key')
    (certs / 'server.crt').write_bytes(cert.public_bytes(pem))
    return created_ca, [str(s.value) for s in sans]


def default_hosts():
    name = socket.gethostname()
    return [name, name.lower(), 'localhost', '127.0.0.1'] + LAN.lan_ipv4()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--host', action='append', default=[], help='extra DNS name or IP address for the certificate')
    ap.add_argument('--enable', action='store_true', help='turn on the HTTPS listener in backend/config.json')
    ap.add_argument('--port', type=int, default=8443)
    a = ap.parse_args(argv)
    hosts = default_hosts() + a.host
    created, names = make(ROOT / 'certs', hosts)
    print(('Created' if created else 'Reused') + ' the office CA: certs/office-ca.crt')
    print('HTTPS certificate: certs/server.crt for ' + ', '.join(names))
    ips = LAN.lan_ipv4()
    url = f'https://{ips[0]}:{a.port}' if ips else f'https://{socket.gethostname()}:{a.port}'
    kit = ROOT / 'certs' / 'employee-pc-kit'
    kit.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'certs' / 'office-ca.crt', kit / 'office-ca.crt')
    if (ROOT / CLIENT_BAT).is_file():
        shutil.copy2(ROOT / CLIENT_BAT, kit / CLIENT_BAT)
    (kit / 'somesh-server-url.txt').write_text(url + '\n', encoding='ascii')
    print('Employee PC kit (copy this folder to each employee PC):', kit)
    if a.enable:
        from restore_db import server_running  # noqa: E402  (same tools folder)
        if server_running(ROOT):
            print('Not changing config.json while the app is running (it would overwrite the change). Close it and re-run with --enable.')
            return 2
        cfg_path = ROOT / 'backend' / 'config.json'
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        (ROOT / 'data' / 'backups').mkdir(parents=True, exist_ok=True)
        shutil.copy2(cfg_path, ROOT / 'data' / 'backups' / f'{stamp}-config.json')
        net = cfg.setdefault('network', {})
        net.setdefault('https', {}).update({'enabled': True, 'port': a.port, 'cert': 'certs/server.crt', 'key': 'certs/server.key'})
        net['https'].setdefault('redirect_lan_http', False)
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'HTTPS enabled on port {a.port} in backend/config.json (previous copy in data/backups/{stamp}-config.json).')
    print('Next: start the app, then on each employee PC run the kit\'s launcher once (it installs office-ca.crt for that user).')
    return 0


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT / 'tools'))
    sys.exit(main())
