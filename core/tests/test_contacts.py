"""Contacts and sending on WhatsApp after approval (made-up numbers)."""

from rishu_core.security.vault import Vault
from rishu_core.tools import comms
from rishu_core.tools.contacts import ContactStore, describe, resolve, save_contact


def run(registry, tool_name, **args):
    tool = registry.get(tool_name)
    clean, problem = tool.clean_args(args)
    assert problem is None, problem
    return tool.handler(**clean)


def test_contacts_are_encrypted_and_matched_carefully(tmp_path):
    def codec(data, protect):
        return bytes(b ^ 9 for b in data)

    store = ContactStore(tmp_path / "contacts.json", vault=Vault(codec))
    assert save_contact(store, "Shruti Kumari", "98765 43210").ok
    assert save_contact(store, "Shruti Verma", "+91 91234 56789").ok
    assert save_contact(store, "Rahul", "").ok
    assert not save_contact(store, "X", "12ab").ok
    assert b"98765" not in (tmp_path / "contacts.json").read_bytes()
    contact, problem = resolve(store, "shruti kumari")
    assert contact["phone"] == "919876543210" and not problem
    contact, problem = resolve(store, "Shruti")
    assert contact is None and "Shruti Kumari" in problem and "Shruti Verma" in problem
    contact, problem = resolve(store, "Rahul")
    assert contact is None and "no WhatsApp number" in problem
    contact, problem = resolve(store, "Neha")
    assert contact is None and "save_contact" in problem
    contact, _ = resolve(store, "9988776655")
    assert contact["phone"] == "919988776655"
    assert "Shruti Kumari (+919876543210)" in describe(
        store, {"to": "Shruti Kumari", "text": "Aaj nahi aa sakta"}
    )


def test_whatsapp_send_opens_the_chat_and_presses_send(registry, opened_urls):
    assert run(registry, "save_contact", name="Shruti", phone="9876543210").ok
    result = run(registry, "whatsapp_send", to="shruti", text="Aaj shaam nahi aa paunga")
    assert result.ok and result.content.startswith("Sent to Shruti")
    assert (
        opened_urls[-1]
        == "whatsapp://send?phone=919876543210&text=Aaj%20shaam%20nahi%20aa%20paunga"
    )
    assert registry.get("whatsapp_send").risk_for({}) == 2  # always the user's approval first
    assert not run(registry, "whatsapp_send", to="Neha", text="hi").ok


def test_when_send_cannot_be_pressed_the_user_is_told():
    opened = []
    contact = {"name": "Shruti", "phone": "919876543210"}
    result = comms.whatsapp_send(
        contact, "hi", lambda u: opened.append(u) or True, lambda: True, lambda: False
    )
    assert result.ok and "could not press Send" in result.content
    result = comms.whatsapp_send(
        contact, "hi", lambda u: opened.append(u) or True, lambda: False, lambda: True
    )
    assert (
        result.ok
        and "not installed" in result.content
        and opened[-1].startswith("https://wa.me/919876543210")
    )
    assert not comms.press_send_in_whatsapp() if __import__("sys").platform != "win32" else True
