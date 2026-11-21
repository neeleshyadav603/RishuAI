"""Phone link: pairing with a code, proof against a man in the middle, device tokens."""

import json
import ssl

import httpx
from fastapi.testclient import TestClient
from test_api import AUTH, make_runtime, read_until

from rishu_core.api import create_app
from rishu_core.api.phone import MAX_TRIES, PhoneLink, fingerprint_of, proof
from rishu_core.security.vault import Vault


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def link(tmp_path, clock=None):
    return PhoneLink(tmp_path, vault=Vault(platform="linux"), clock=clock or Clock())


def test_pairing_code_proof_and_device_tokens(tmp_path):
    clock = Clock()
    phone = link(tmp_path, clock)
    assert phone.hello()["pairing"] is False and "proof" not in phone.hello()
    info = phone.start_pairing()
    assert len(info["code"]) == 6 and info["fingerprint"] == fingerprint_of(phone.cert)
    # The phone checks the proof against the certificate it sees.
    assert phone.hello()["proof"] == proof(info["code"], info["fingerprint"])
    assert phone.hello()["proof"] != proof(info["code"], "f" * 64)  # another certificate
    assert phone.pair("000000" if info["code"] != "000000" else "111111", "x") is None
    token = phone.pair(info["code"], "Neelesh  phone")
    assert token and phone.device_for(token)["name"] == "Neelesh phone"
    assert phone.pair(info["code"], "again") is None  # one phone per code
    assert token not in (tmp_path / "phone" / "devices.json").read_text()  # only a hash is stored
    device = phone.devices()[0]
    assert phone.remove(device["id"]) and phone.device_for(token) is None


def test_codes_expire_and_guessing_is_limited(tmp_path):
    clock = Clock()
    phone = link(tmp_path, clock)
    code = phone.start_pairing()["code"]
    wrong = "123456" if code != "123456" else "654321"
    for _ in range(MAX_TRIES):
        assert phone.pair(wrong, "x") is None
    assert phone.pair(code, "x") is None  # locked after too many tries
    code = phone.start_pairing()["code"]
    clock.now += 601
    assert phone.pair(code, "x") is None and not phone.pairing_active()


def test_remote_app_needs_a_device_token_and_never_uses_the_pc_mic(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path, script=["Namaste!"])
    remote = TestClient(create_app(runtime, remote=True))
    assert (
        remote.get("/v1/settings", headers=AUTH).status_code == 401
    )  # the laptop's session token is not enough
    assert remote.get("/v1/phone/hello").json()["pairing"] is False
    code = runtime.phone.start_pairing()["code"]
    assert (
        remote.post(
            "/v1/phone/pair",
            json={"code": "999999" if code != "999999" else "000000", "device": "p"},
        ).status_code
        == 403
    )
    token = remote.post("/v1/phone/pair", json={"code": code, "device": "Pixel"}).json()["token"]
    phone_auth = {"Authorization": f"Bearer {token}"}
    assert remote.get("/v1/settings", headers=phone_auth).status_code == 200
    with remote.websocket_connect("/ws", headers=phone_auth) as ws:
        read_until(ws, "hello")
        ws.send_text(json.dumps({"v": 1, "type": "listen_start"}))
        assert read_until(ws, "error")[-1]["code"] == "voice_remote"
        ws.send_text(json.dumps({"v": 1, "type": "user_message", "text": "Namaste"}))
        assert read_until(ws, "assistant_message")[-1]["text"] == "Namaste!"
        assert runtime.active_session.remote is True
    # The laptop app manages the link; the phone app cannot.
    local = TestClient(create_app(runtime))
    status = local.get("/v1/phone", headers=AUTH).json()
    assert status["devices"][0]["name"] == "Pixel"
    assert remote.get("/v1/phone", headers=phone_auth).status_code == 404


def test_phone_link_serves_tls_on_the_lan(settings, registry, tmp_path):
    runtime = make_runtime(settings, registry, tmp_path, script=[])
    try:
        info = runtime.start_phone_link()
        port = runtime.phone.port
        for _ in range(50):
            try:
                pem = ssl.get_server_certificate(("127.0.0.1", port), timeout=1)
                break
            except OSError:
                import time

                time.sleep(0.1)
        der = ssl.PEM_cert_to_DER_cert(pem)
        import hashlib

        seen = hashlib.sha256(der).hexdigest()
        assert seen == info["fingerprint"]
        hello = httpx.get(
            f"https://127.0.0.1:{port}/v1/phone/hello", verify=False, timeout=5
        ).json()
        assert hello["proof"] == proof(info["code"], seen)
    finally:
        runtime.stop_phone_link()
