"""One app connection: its agent, its running turn and its pending approvals."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from ..agent import Agent, ApprovalRequest
from ..permissions import Risk
from ..security import is_panic_phrase
from ..strings import t
from ..voice import MicError, Speaker, SttError, is_goodbye, to_wav
from .runtime import PROTOCOL_VERSION, CoreRuntime

Event = dict[str, Any]


class SessionApprover:
    """Waits for the user's answer to an approval card.

    The agent thread blocks in :meth:`confirm`; the connection calls
    :meth:`resolve` when ``approval_response`` arrives. No answer within the
    timeout, a closed connection or STOP all count as "no".
    """

    def __init__(
        self,
        timeout: float,
        on_step_up_blocked: Callable[[ApprovalRequest], None],
        step_up_ready: Callable[[], bool] = lambda: False,
        verify_step_up: Callable[[str], bool] = lambda pin: False,
    ):
        self.timeout = timeout
        self._on_step_up_blocked = on_step_up_blocked
        self._step_up_ready = step_up_ready
        self._verify_step_up = verify_step_up
        self._cond = threading.Condition()
        self._expected: set[str] = set()
        self._answers: dict[str, bool] = {}
        self._pins: dict[str, str] = {}
        self._cancelled = False

    def expect(self, call_id: str) -> None:
        """An approval card for ``call_id`` is on its way to the app."""
        with self._cond:
            self._expected.add(call_id)

    def confirm(self, request: ApprovalRequest) -> bool:
        call_id = request.call_id
        with self._cond:
            self._expected.add(call_id)
            self._cond.wait_for(lambda: call_id in self._answers or self._cancelled, self.timeout)
            self._expected.discard(call_id)
            answer = self._answers.pop(call_id, False)
            return answer and not self._cancelled  # STOP wins over a late "yes"

    def step_up(self, request: ApprovalRequest) -> bool:
        """R3: the user approves on the card with Rishu's PIN, then Windows Hello.

        Two different factors (spec §6): the PIN Rishu knows, and Windows Hello
        (fingerprint, face or the Windows PIN of this device). Without both set
        up, the answer is no.
        """
        if not self._step_up_ready():
            self._on_step_up_blocked(request)
            return False
        if not self.confirm(request):
            return False
        with self._cond:
            pin = self._pins.pop(request.call_id, "")
        return bool(pin) and self._verify_step_up(pin)

    def resolve(self, call_id: str, approved: bool, pin: str | None = None) -> bool:
        """Record the user's answer. Returns False when nothing was waiting for it."""
        with self._cond:
            if call_id not in self._expected or call_id in self._answers:
                return False
            self._answers[call_id] = bool(approved)
            if pin:
                self._pins[call_id] = pin
            self._cond.notify_all()
            return True

    def cancel_all(self) -> None:
        """Answer "no" to everything that is waiting (STOP or disconnect)."""
        with self._cond:
            self._cancelled = True
            self._cond.notify_all()

    def reset(self) -> None:
        with self._cond:
            self._cancelled = False
            self._expected.clear()
            self._answers.clear()


class Session:
    def __init__(self, runtime: CoreRuntime, send: Callable[[Event], None]):
        self.runtime = runtime
        self._send = send  # thread-safe: called from the agent thread
        self.approver = SessionApprover(
            runtime.server_option("approval_timeout_seconds", 120.0),
            self._step_up_blocked,
            step_up_ready=runtime.lock.step_up_ready,
            verify_step_up=self._verify_step_up,
        )
        self._agent: Agent | None = None
        self._generation = -1
        self._turn = threading.Lock()
        self._proposals: dict[str, Event] = {}
        self._closed = False
        self._speech_pending = False
        self._voice_turn = False  # the current exchange started by voice
        voice = runtime.voice
        self.speaker = Speaker(
            voice.synthesizer,
            voice.player,
            voice.workdir,
            on_state=self._speech_state,
            on_error=self._speech_error,
        )
        self.recorder = voice.new_recorder()
        runtime.attach(self)

    # ---- helpers -------------------------------------------------------

    def _language(self) -> str:
        return self._agent.language if self._agent else "hinglish"

    def _emit(self, event: Event) -> None:
        if event.get("type") == "tool_call_proposed":
            if event.get("decision") == "step_up":
                event = {**event, "step_up_ready": self.runtime.lock.step_up_ready()}
            self._proposals[event["call_id"]] = event
            if event.get("decision") == "confirm" or event.get("step_up_ready"):
                self.approver.expect(event["call_id"])
        kind = event.get("type")
        if kind == "state_change" and event.get("state") == "idle" and self._speech_pending:
            # The reply is about to be spoken: go straight to "speaking", no idle flicker.
            self._speech_pending = False
            event = {**event, "state": "speaking"}
        self._send(event)
        if kind == "assistant_message" and not self._closed:
            text = event.get("text") or ""
            settings = self.runtime.public_settings()
            if text and settings.get("speak_replies"):
                self._speech_pending = self.speaker.say(text, settings.get("voice_gender", "male"))

    def _state(self, state: str) -> None:
        self._send({"v": PROTOCOL_VERSION, "type": "state_change", "state": state})

    def _speech_state(self, state: str) -> None:
        if self._closed:
            return
        self._state(state)
        if state == "idle" and self._voice_turn and self._follow_up_wanted():
            # Conversation mode: the spoken reply ended by itself, so listen again.
            threading.Thread(target=self.listen, kwargs={"follow_up": True}, daemon=True).start()

    def _follow_up_wanted(self) -> bool:
        return (
            self.runtime.public_settings().get("follow_up") is True
            and not self.busy
            and not self.runtime.lock.locked
            and not self.recorder.active
        )

    def _speech_error(self, message: str) -> None:
        if not self._closed:
            self.error("voice_output", f"{t('voice_output_failed', self._language())} ({message}).")

    def error(self, code: str, message: str) -> None:
        self._send({"v": PROTOCOL_VERSION, "type": "error", "code": code, "message": message})

    def _verify_step_up(self, pin: str) -> bool:
        lock = self.runtime.lock
        ok, code = lock.check_pin(pin)
        if not ok:
            key = "unlock_paused" if code == "paused" else "step_up_wrong_pin"
            self.error(f"step_up_{code}", t(key, self._language()))
            return False
        self._send(
            {"v": PROTOCOL_VERSION, "type": "notice", "text": t("step_up_hello", self._language())}
        )
        if lock.hello is None or not lock.hello.verify(
            "Rishu: is kaam ko approve karne ke liye pehchaan dikhao"
        ):
            self.error("step_up_hello_failed", t("step_up_hello_failed", self._language()))
            return False
        return True

    def _step_up_blocked(self, request: ApprovalRequest) -> None:
        self._send(
            {
                "v": PROTOCOL_VERSION,
                "type": "notice",
                "text": t("step_up_unavailable", self._language()),
            }
        )

    def _ensure_agent(self) -> Agent:
        """Build the agent, or rebuild it after a settings change, keeping the conversation."""
        if self._agent is None or self._generation != self.runtime.generation:
            generation = self.runtime.generation
            history = self._agent.history if self._agent else []
            trusted = self._agent.permissions.trusted_skills if self._agent else set()
            self._agent = self.runtime.build_agent(self.approver, self._emit)
            self._agent.history = history
            self._agent.permissions.trusted_skills |= trusted
            self._generation = generation
        return self._agent

    # ---- events from the app -------------------------------------------

    @property
    def busy(self) -> bool:
        return self._turn.locked()

    def try_begin_turn(self) -> bool:
        """Reserve the turn slot. Call from the connection before starting the worker."""
        return self._turn.acquire(blocking=False)

    def run_turn(self, text: str, voice: bool = False) -> None:
        """Run one user turn. Blocking: call in a worker thread after try_begin_turn."""
        self._voice_turn = voice
        try:
            self.approver.reset()
            self._proposals.clear()
            agent = self._ensure_agent()
            if self._closed:
                return
            agent.run_turn(text)
        except Exception as exc:  # noqa: BLE001 - never let a turn kill the connection
            self.error("internal", f"Something went wrong inside Rishu ({type(exc).__name__}).")
            self._send({"v": PROTOCOL_VERSION, "type": "state_change", "state": "idle"})
        finally:
            self._turn.release()

    def stop(self) -> None:
        self._voice_turn = False  # STOP also ends conversation mode
        self.recorder.cancel()
        self.stop_speaking()
        self.approver.cancel_all()
        if self._agent is not None:
            self._agent.stop()

    # ---- voice ---------------------------------------------------------

    def listen(self, follow_up: bool = False) -> None:
        """Push-to-talk: record, transcribe, then run the turn. Blocking (worker thread).

        ``follow_up``: conversation mode re-opened the mic after a spoken reply;
        silence then simply ends the conversation, without a notice.
        """
        self._voice_turn = False
        if self.runtime.lock.locked:
            self.unlock_by_voice()
            return
        self.runtime.lock.touch()
        status = self.runtime.voice.status()
        if not status["input"]:
            reason = status.get("input_reason") or ""
            self.error("voice_unavailable", f"{t('voice_input_off', self._language())}: {reason}.")
            return
        self.stop_speaking()  # barge-in: the user wants to talk now
        if self.busy:
            self.error("busy", "Rishu is still working on the previous message.")
            return
        if self.recorder.active:
            return
        self._state("listening")
        try:
            recording = self.recorder.record(
                on_level=self._audio_level, no_speech_seconds=6.0 if follow_up else None
            )
        except MicError as exc:
            self.error("voice_mic", str(exc))
            self._state("idle")
            return
        if recording.cancelled or self._closed:
            self._state("idle")
            return
        if not recording.heard_speech:
            if not follow_up or recording.silent:
                self._not_heard(recording)
            self._state("idle")
            return
        self._state("thinking")
        language = "en" if self.runtime.public_settings().get("language") == "en" else "hi"
        try:
            transcriber = self.runtime.voice.transcriber()
            try:
                text = transcriber.transcribe(to_wav(recording.pcm), language=language)
            finally:
                transcriber.close()
        except SttError as exc:
            self.error(f"voice_{exc.code}", str(exc))
            self._state("idle")
            return
        if not text.strip() or self._closed:
            if not follow_up:
                self._send(
                    {
                        "v": PROTOCOL_VERSION,
                        "type": "notice",
                        "text": t("not_heard", self._language()),
                    }
                )
            self._state("idle")
            return
        if follow_up and is_goodbye(text):
            self._send(
                {
                    "v": PROTOCOL_VERSION,
                    "type": "transcript_final",
                    "text": text,
                    "language": language,
                }
            )
            self.speaker.say(
                t("goodbye", self._language()),
                self.runtime.public_settings().get("voice_gender", "male"),
            )
            return
        self._send(
            {"v": PROTOCOL_VERSION, "type": "transcript_final", "text": text, "language": language}
        )
        if self.handle_text(text) != "ok":
            if self.runtime.lock.locked:
                return
            self._state("idle")
            return
        if not self.try_begin_turn():
            self.error("busy", "Rishu is still working on the previous message.")
            return
        self.run_turn(text, voice=True)

    def _audio_level(self, level: float) -> None:
        self._send({"v": PROTOCOL_VERSION, "type": "audio_level", "level": round(level, 3)})

    def listen_stop(self) -> None:
        self.recorder.finish()

    def send_event(self, event: dict[str, Any]) -> None:
        """An event from a tool (teach mode) for the app."""
        if not self._closed:
            self._send({"v": PROTOCOL_VERSION, **event})

    # ---- lock --------------------------------------------------------------

    def send_lock_state(self) -> None:
        self._send({"v": PROTOCOL_VERSION, "type": "lock_state", **self.runtime.lock.status()})

    def locked(self) -> None:
        """Rishu was just locked: stop everything and tell the app."""
        self.stop()
        if self._agent is not None and not self.busy:
            self._agent.reset()  # a locked screen must not keep the conversation
        self.send_lock_state()
        self._state("locked")

    def notice_lock_needs_pin(self) -> None:
        self._send(
            {"v": PROTOCOL_VERSION, "type": "notice", "text": t("lock_needs_pin", self._language())}
        )

    def unlock(self, method: str, pin: str | None) -> None:
        """PIN or Windows Hello unlock (Hello blocks while its dialog is open)."""
        lock = self.runtime.lock
        if method == "pin":
            ok, code = lock.unlock_pin(pin or "")
        else:
            ok, code = lock.unlock_hello()
        self.send_lock_state()
        if ok:
            self._state("idle")
            return
        key = {"paused": "unlock_paused", "no_hello": "unlock_no_hello"}.get(code, "unlock_failed")
        self.error(f"unlock_{code}", t(key, self._language()))

    def announce_locked_reminder(self) -> None:
        """A reminder is due while locked: say so without reading it out."""
        self.speaker.say(
            t("reminder_while_locked", self._language()),
            self.runtime.public_settings().get("voice_gender", "male"),
        )

    def handle_text(self, text: str) -> str:
        """Before a turn: 'ok' to run it, 'handled' when done here, or 'locked'."""
        lock = self.runtime.lock
        if is_panic_phrase(text):
            if not self.runtime.lock_now():
                self.notice_lock_needs_pin()
            return "handled"
        if lock.locked:
            self.error("locked", t("locked", self._language()))
            return "locked"
        lock.touch()
        return "ok"

    def unlock_by_voice(self) -> None:
        """While locked, the mic hears the spoken password. Blocking (worker thread)."""
        lock = self.runtime.lock
        if not lock.phrase_set:
            self.error("locked", t("locked", self._language()))
            return
        text = self._record_and_transcribe()
        if text is None:
            return
        ok, code = lock.unlock_phrase(text)
        self.send_lock_state()
        self._state("idle" if ok else "locked")
        if not ok:
            key = "unlock_paused" if code == "paused" else "unlock_failed"
            self.error(f"unlock_{code}", t(key, self._language()))

    def enroll_phrase(self) -> dict[str, Any]:
        """Record the spoken password (Settings). Blocking."""
        text = self._record_and_transcribe()
        if not text:
            return {"ok": False, "code": "not_heard"}
        try:
            self.runtime.lock.set_phrase(text)
        except (ValueError, PermissionError) as exc:
            self._state("idle")
            key = "phrase_too_short" if isinstance(exc, ValueError) else "lock_needs_pin"
            self.error("phrase_invalid", t(key, self._language()))
            return {"ok": False, "code": "invalid"}
        self._state("idle")
        self.send_lock_state()
        self._send(
            {"v": PROTOCOL_VERSION, "type": "notice", "text": t("phrase_saved", self._language())}
        )
        return {"ok": True}

    def _not_heard(self, recording: Any) -> None:
        if getattr(recording, "silent", False):
            self.error("voice_mic_silent", t("mic_silent", self._language()))
        else:
            self._send(
                {"v": PROTOCOL_VERSION, "type": "notice", "text": t("not_heard", self._language())}
            )

    def _record_and_transcribe(self) -> str | None:
        status = self.runtime.voice.status()
        after = "locked" if self.runtime.lock.locked else "idle"
        if not status["input"]:
            reason = status.get("input_reason") or ""
            self.error("voice_unavailable", f"{t('voice_input_off', self._language())}: {reason}.")
            return None
        if self.recorder.active:
            return None
        self.stop_speaking()
        self._state("listening")
        try:
            recording = self.recorder.record(on_level=self._audio_level)
        except MicError as exc:
            self.error("voice_mic", str(exc))
            self._state(after)
            return None
        if recording.cancelled or not recording.heard_speech or self._closed:
            if not recording.cancelled:
                self._not_heard(recording)
            self._state(after)
            return None
        self._state("thinking")
        language = "en" if self.runtime.public_settings().get("language") == "en" else "hi"
        try:
            transcriber = self.runtime.voice.transcriber()
            try:
                return transcriber.transcribe(to_wav(recording.pcm), language=language)
            finally:
                transcriber.close()
        except SttError as exc:
            self.error(f"voice_{exc.code}", str(exc))
            self._state(after)
            return None

    def deliver_reminder(self, text: str) -> None:
        self._send({"v": PROTOCOL_VERSION, "type": "reminder", "text": text})
        spoken = f"Reminder: {text}" if self._language() == "en" else f"Yaad dila raha hoon: {text}"
        self.speaker.say(spoken, self.runtime.public_settings().get("voice_gender", "male"))

    def toggle_listening(self) -> None:
        """Global shortcut: stop listening if listening, else start in the background."""
        if self.recorder.active:
            self.listen_stop()
        elif not self.busy:
            threading.Thread(target=self.listen, name="rishu-listen", daemon=True).start()

    def speak(self, text: str) -> None:
        if self.runtime.lock.locked:
            return
        if not self.speaker.say(text, self.runtime.public_settings().get("voice_gender", "male")):
            self.error("voice_output", t("voice_output_failed", self._language()) + ".")

    def stop_speaking(self) -> None:
        was_speaking = self.speaker.speaking
        self._speech_pending = False
        self.speaker.stop(wait=0)
        if was_speaking and not self.busy and not self._closed:
            self._state("idle")

    def approval(
        self, call_id: str, approved: bool, always_allow: bool = False, pin: str | None = None
    ) -> None:
        proposal = self._proposals.get(call_id)
        if not self.approver.resolve(call_id, approved, pin):
            self.error("no_such_approval", "That approval is no longer waiting.")
            return
        # "Always allow" marks the skill as trusted for this session. It never
        # applies to R3, and the permission engine honours it only in the
        # trusted_skills autonomy mode and never after untrusted content.
        if (
            approved
            and always_allow
            and proposal is not None
            and proposal.get("skill")
            and proposal.get("risk") != Risk.R3.label
            and self._agent is not None
        ):
            self._agent.permissions.trusted_skills.add(proposal["skill"])

    def new_conversation(self) -> None:
        if self._agent is not None and not self.busy:
            self._agent.reset()

    def close(self) -> None:
        self._closed = True
        self.runtime.detach(self)
        self.stop()
