"""Contract tests: the shared fixtures and everything the agent emits match the schema.

The Dart side parses the same fixtures in ``app/test/protocol_test.dart``.
"""

import json
from pathlib import Path

import jsonschema
import pytest

PROTOCOL = Path(__file__).resolve().parents[2] / "shared" / "protocol"
SCHEMA = json.loads((PROTOCOL / "events.schema.json").read_text(encoding="utf-8"))
FIXTURES = json.loads((PROTOCOL / "fixtures.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def test_schema_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f"{f['dir']}:{f['event']['type']}")
def test_fixture_matches_the_schema(fixture):
    assert fixture["dir"] in ("a2c", "c2a")
    VALIDATOR.validate(fixture["event"])


def test_every_event_type_has_a_fixture():
    defined = {ref["$ref"].split("/")[-1] for ref in SCHEMA["oneOf"]}
    covered = {fixture["event"]["type"] for fixture in FIXTURES}
    assert defined == covered


@pytest.mark.parametrize(
    "event",
    [
        {"type": "user_message", "text": "no version"},
        {"v": 2, "type": "stop"},
        {"v": 1, "type": "user_message"},
        {"v": 1, "type": "state_change", "state": "dancing"},
        {
            "v": 1,
            "type": "tool_call_proposed",
            "call_id": "c",
            "tool": "t",
            "args": {},
            "risk": "R9",
            "decision": "confirm",
            "preview": "p",
        },
        {"v": 1, "type": "made_up"},
    ],
)
def test_schema_rejects_malformed_events(event):
    assert list(VALIDATOR.iter_errors(event))
