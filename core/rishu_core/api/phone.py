"""Phone link: the Android app talks to the laptop's Rishu over the home Wi-Fi.

Off by default. When the user turns it on, the core also listens on the LAN
with TLS (a self-signed certificate made on this PC). Pairing uses a 6-digit
code shown in the laptop app and valid for 10 minutes:

1. The phone asks ``/v1/phone/hello`` and gets HMAC(code, certificate
   fingerprint). It computes the same over the certificate it actually sees;
   a man in the middle (another certificate) cannot produce a matching value
   without the code, so the phone stops before sending anything.
2. The phone sends the code to ``/v1/phone/pair`` and receives a device token.
   It then pins the certificate fingerprint for every later connection.

Device tokens are stored only as SHA-256 hashes; the user can remove a phone
at any time. A UDP beacon lets the phone find the laptop on the same Wi-Fi.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..security.vault import Vault, default_vault

PAIR_SECONDS = 600
MAX_TRIES = 5
DEFAULT_PORT = 47800
BEACON_PORT = 47801


def lan_addresses() -> list[str]:
    """IPv4 addresses of this PC on local networks (not loopback)."""
    found: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))  # no packet is sent: picks the outgoing interface
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in found:
                found.append(address)
    except OSError:
        pass
    return [a for a in found if not a.startswith("127.")]


def make_certificate(cert_path: Path, key_path: Path) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Rishu")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def fingerprint_of(cert_path: Path) -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def proof(code: str, fingerprint: str) -> str:
    return hmac.new(code.encode(), fingerprint.encode(), hashlib.sha256).hexdigest()


class PhoneLink:
    def __init__(
        self, home: Path, *, vault: Vault | None = None, clock: Callable[[], float] = time.time
    ):
        self.folder = home / "phone"
        self.cert = self.folder / "cert.pem"
        self.key = self.folder / "key.pem"
        self._devices = self.folder / "devices.json"
        self.vault = vault or default_vault()
        self._clock = clock
        self._lock = threading.Lock()
        self._code: str | None = None
        self._code_until = 0.0
        self._tries = 0
        self.port = DEFAULT_PORT
        self.running = False

    # ---- certificate ---------------------------------------------------------------

    def ensure_certificate(self) -> str:
        if not (self.cert.exists() and self.key.exists()):
            make_certificate(self.cert, self.key)
        return fingerprint_of(self.cert)

    # ---- pairing ---------------------------------------------------------------------

    def start_pairing(self) -> dict[str, Any]:
        fingerprint = self.ensure_certificate()
        with self._lock:
            self._code = f"{secrets.randbelow(1_000_000):06d}"
            self._code_until = self._clock() + PAIR_SECONDS
            self._tries = 0
        return {
            "code": self._code,
            "expires_in": PAIR_SECONDS,
            "addresses": lan_addresses(),
            "port": self.port,
            "fingerprint": fingerprint,
        }

    def pairing_active(self) -> bool:
        return self._code is not None and self._clock() < self._code_until

    def hello(self) -> dict[str, Any]:
        """What an unpaired phone may see: the PC's name and, while pairing, the proof."""
        info: dict[str, Any] = {
            "name": f"Rishu on {socket.gethostname()}",
            "pairing": self.pairing_active(),
        }
        if self.pairing_active() and self._code:
            info["proof"] = proof(self._code, fingerprint_of(self.cert))
        return info

    def pair(self, code: str, device: str) -> str | None:
        with self._lock:
            if not self.pairing_active() or self._code is None:
                return None
            self._tries += 1
            if self._tries > MAX_TRIES:
                self._code = None  # too many wrong codes: start again on the laptop
                return None
            if not hmac.compare_digest(code.strip(), self._code):
                return None
            self._code = None  # one phone per code
            token = secrets.token_urlsafe(32)
            devices = self._load()
            devices.append(
                {
                    "id": secrets.token_hex(4),
                    "name": " ".join(device.split())[:40] or "Phone",
                    "token": hashlib.sha256(token.encode()).hexdigest(),
                    "paired": self._clock(),
                }
            )
            self._save(devices)
            return token

    # ---- devices -----------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.vault.read_text(self._devices) or "[]")
        except ValueError:
            return []
        return (
            [d for d in data if isinstance(d, dict) and d.get("token")]
            if isinstance(data, list)
            else []
        )

    def _save(self, devices: list[dict[str, Any]]) -> None:
        self.vault.write_text(self._devices, json.dumps(devices))

    def device_for(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        return next((d for d in self._load() if hmac.compare_digest(d["token"], digest)), None)

    def devices(self) -> list[dict[str, Any]]:
        return [{"id": d["id"], "name": d["name"], "paired": d["paired"]} for d in self._load()]

    def remove(self, device_id: str) -> bool:
        devices = self._load()
        kept = [d for d in devices if d["id"] != device_id]
        if len(kept) == len(devices):
            return False
        self._save(kept)
        return True

    def status(self) -> dict[str, Any]:
        return {
            "type": "phone_link",
            "running": self.running,
            "port": self.port,
            "addresses": lan_addresses() if self.running else [],
            "pairing": self.pairing_active(),
            "devices": self.devices(),
        }


def beacon(link: PhoneLink, stop: threading.Event, interval: float = 2.0) -> None:
    """Tell phones on the same Wi-Fi where Rishu is (no secrets in the message)."""
    message = json.dumps({"rishu": 1, "port": link.port, "name": socket.gethostname()}).encode()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not stop.wait(interval):
            try:
                sock.sendto(message, ("255.255.255.255", BEACON_PORT))
            except OSError:
                pass
