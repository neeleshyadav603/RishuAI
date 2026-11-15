# Rishu — build progress

Checkpoint file. Every session reads this first and updates it with every push.
Rules for sessions are in `CLAUDE.md`.

**Current phase:** 1 (Brain)
**Last updated:** 2026-11-16

## Phase 0 — Setup

- [x] Repo structure, `CLAUDE.md`, `RISHU_SPEC.md`, SRS PDF in `docs/`
- [x] `config/` (models, policy, defaults, app aliases)
- [x] `shared/prompts/` (persona, system rules), `shared/protocol/events.schema.json`
- [x] `scripts/test_all.sh`, `scripts/test_all.ps1`, `scripts/dev.ps1`
- [x] CI workflow: lint + tests on Linux and Windows
- [ ] App skeleton started by `dev.ps1` (moves to Phase 2 with the Flutter app)

## Phase 1 — Brain (desktop core, text chat)

- [ ] LLM provider client (OpenAI-compatible) + router with quota fallback
- [ ] Permission engine R0–R3, autonomy modes, untrusted-content rule
- [ ] Tool registry + tools: open_app, open_url, web_search, read_page, get_time, notes
- [ ] Agent loop with tool calls, approvals, STOP, activity log
- [ ] Offline intent fallback (open app, time, note) when no LLM is reachable
- [ ] CLI text chat (`python -m rishu_core`)
- [ ] Tests: mock-LLM agent flows, 429 fallback, permissions, tools
- [ ] Acceptance: "Chrome kholo" and "AI news search karo" (with sources) work in text

## Phase 2 — App + Voice (Windows)

- [ ] FastAPI + WebSocket server in the core, implementing `shared/protocol`
- [ ] Flutter app: home with animated orb, conversation, cards, settings, onboarding
- [ ] Voice: STT (faster-whisper, Groq option), TTS (edge-tts + offline fallback), hotkey, barge-in
- [ ] GitHub Actions: Windows build (Flutter + PyInstaller + Inno Setup) → `RishuSetup.exe`
- [ ] GitHub Actions: Android debug APK from the same app (pipeline check)

## Phases 3–10

See spec §14. Break each phase into checklist items here when it starts.

## Needs device test (cannot be verified in the cloud workspace)

- Nothing yet.

## Known issues

- None yet.

## Additions beyond the spec

- Offline intent fallback in the core (Phase 1): basic Hinglish/Hindi/English
  commands still work when no LLM provider is reachable.

## Ideas backlog (owner gave freedom to add features)

- "Why did you do that?": Rishu explains the last action from the activity log.
- Dry-run mode: Rishu says what it would do without doing it.
- Command palette in the desktop app (Ctrl+K) for typed quick actions.
- Privacy dashboard: one screen showing what is stored and what left the device.
- Clipboard quick actions: summarise, translate or explain the copied text.
- Conversation export to PDF/Markdown; shareable tutor notes.
- First-run interactive tour and sample commands in Hindi and English.

## Decisions log

- 2026-11-16: Builds for Windows and Android run on GitHub Actions; the cloud
  workspace cannot download Flutter or the Android SDK.
- 2026-11-16: Work is pushed straight to `main` (owner's own repo, created empty
  for this project; scheduled sessions and Releases need one stable branch).
- 2026-11-16: No open-source license file yet. The repo is public but the owner
  plans a business; licensing is the owner's decision.
