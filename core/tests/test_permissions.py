import pytest

from rishu_core.permissions import Decision, PermissionEngine, Risk

POLICY = {
    "default_autonomy": "smart",
    "untrusted_bump": 1,
    "forbidden_tools": ["complete_payment"],
    "max_auto_risk": 2,
}


def decide(engine, risk, **kwargs):
    return engine.evaluate("some_tool", risk, **kwargs).decision


def test_smart_mode_levels():
    engine = PermissionEngine(POLICY)
    assert decide(engine, Risk.R0) == Decision.ALLOW
    assert decide(engine, Risk.R1) == Decision.ALLOW_NOTIFY
    assert decide(engine, Risk.R2) == Decision.CONFIRM
    assert decide(engine, Risk.R3) == Decision.STEP_UP


def test_ask_always_confirms_low_risk():
    engine = PermissionEngine(POLICY, autonomy="ask_always")
    assert decide(engine, Risk.R0) == Decision.ALLOW
    assert decide(engine, Risk.R1) == Decision.CONFIRM


def test_forbidden_tool_is_refused_in_every_mode():
    for mode in ("ask_always", "smart", "trusted_skills"):
        engine = PermissionEngine(POLICY, autonomy=mode, trusted_skills={"pay"})
        verdict = engine.evaluate("complete_payment", Risk.R0, skill="pay")
        assert verdict.decision == Decision.FORBID


def test_untrusted_content_raises_risk_by_one_level():
    engine = PermissionEngine(POLICY)
    assert decide(engine, Risk.R0, tainted=True) == Decision.ALLOW  # reading more is fine
    assert decide(engine, Risk.R1, tainted=True) == Decision.CONFIRM
    assert decide(engine, Risk.R2, tainted=True) == Decision.STEP_UP
    assert engine.evaluate("t", Risk.R3, tainted=True).risk == Risk.R3


def test_trusted_skill_runs_r2_without_asking():
    engine = PermissionEngine(POLICY, autonomy="trusted_skills", trusted_skills={"send_whatsapp"})
    assert decide(engine, Risk.R2, skill="send_whatsapp") == Decision.ALLOW_NOTIFY
    assert decide(engine, Risk.R2, skill="other") == Decision.CONFIRM
    # Trust never applies after untrusted content, and never to R3.
    assert decide(engine, Risk.R2, skill="send_whatsapp", tainted=True) == Decision.STEP_UP
    assert decide(engine, Risk.R3, skill="send_whatsapp") == Decision.STEP_UP


def test_trusted_skills_ignored_outside_that_mode():
    engine = PermissionEngine(POLICY, autonomy="smart", trusted_skills={"send_whatsapp"})
    assert decide(engine, Risk.R2, skill="send_whatsapp") == Decision.CONFIRM


def test_policy_cannot_make_r3_automatic():
    engine = PermissionEngine(
        {**POLICY, "max_auto_risk": 3}, autonomy="trusted_skills", trusted_skills={"wipe"}
    )
    assert decide(engine, Risk.R3, skill="wipe") == Decision.STEP_UP


def test_unknown_autonomy_mode_is_rejected():
    with pytest.raises(ValueError):
        PermissionEngine(POLICY, autonomy="yolo")
