# Rishu — build progress

Checkpoint file. Every session reads this first and updates it with every push.
Rules for sessions are in `CLAUDE.md`.

**Current phase:** 2 (App + Voice)
**Last updated:** 2026-11-16

## Phase 0 — Setup

- [x] Repo structure, `CLAUDE.md`, `RISHU_SPEC.md`, SRS PDF in `docs/`
- [x] `config/` (models, policy, defaults, app aliases)
- [x] `shared/prompts/` (persona, system rules), `shared/protocol/events.schema.json`
- [x] `scripts/test_all.sh`, `scripts/test_all.ps1`, `scripts/dev.ps1`
- [x] CI workflow: lint + tests on Linux and Windows
- [ ] App skeleton started by `dev.ps1` (moves to Phase 2 with the Flutter app)

## Phase 1 — Brain (desktop core, text chat)

- [x] LLM provider client (OpenAI-compatible) + router with quota fallback
- [x] Permission engine R0–R3, autonomy modes, untrusted-content rule
- [x] Tool registry + tools: open_app, open_url, web_search, read_page, get_time, notes
- [x] Agent loop with tool calls, approvals, STOP, activity log
- [x] Offline intent fallback (open app, time, note) when no LLM is reachable
- [x] CLI text chat (`python -m rishu_core`)
- [x] Tests: mock-LLM agent flows, 429 fallback, permissions, tools (77 tests)
- [x] Acceptance with the scripted model: "Chrome kholo" and "AI news search karo"
      (with sources) pass in `core/tests/test_agent.py`
- [ ] Acceptance with a real LLM and a real Windows PC (see "Needs device test")

Phase 1 leftovers to pick up in Phase 2/3:
- API keys are read from environment variables only; the OS secure store
  (DPAPI / keyring) comes with onboarding in Phase 2/3.
- `open_app` indexes Start-menu shortcuts and aliases; Store (UWP) apps without a
  shortcut need `Get-StartApps` support.
- Agent is synchronous; the WebSocket server runs it in a worker thread and adds
  token streaming.

## Phase 2 — App + Voice (Windows)

Build pipeline (proven on 2026-11-16, run 43755862637: APK 14 MB, installer 35 MB,
packaged core passes `--selftest` on Windows):
- [x] GitHub Actions: Windows build (Flutter + PyInstaller + Inno Setup) → `RishuSetup-x.y.z.exe`
- [x] GitHub Actions: Android release APK (arm64) with the 30 MB size gate
- [ ] Commit the platform folders: download the `scaffold-android` and
      `scaffold-windows` artifacts of the latest "Build apps" run
      (`gh run download <id> -n scaffold-android -D app/android`, same for windows),
      commit them, then set the app name "Rishu", the Android permissions and the
      icons there. Until then CI generates them on every run.
- [ ] Release workflow: on a `v*` tag, publish the installer and APK to GitHub Releases
- [ ] Release APK signing with a real keystore from GitHub Secrets (owner must
      create the secret; until then the APK is signed with the debug key)

Core server:
- [ ] FastAPI + WebSocket server in the core, implementing `shared/protocol`
      (agent runs in a worker thread; approvals travel as `tool_call_proposed` /
      `approval_response`; `stop` calls `Agent.stop()`)
- [ ] Token streaming from the provider client to `assistant_token` events
- [ ] The Windows app starts the bundled core (`core\rishu-core.exe`) and connects
      with a session token on 127.0.0.1

Flutter app (must be highly interactive and polished):
- [ ] App structure: Riverpod, routing, theme (dark/light), i18n (English, Hindi, Hinglish)
- [ ] Home with the animated orb reacting to state (idle/listening/thinking/speaking/acting/locked/offline)
- [ ] Conversation view with streaming text and cards: action confirm, sources, progress, error
- [ ] Onboarding: language, name, provider + API key with a Test button, permissions
- [ ] Settings: providers/models, autonomy mode, voice, about
- [ ] Always-visible STOP while an action runs
- [ ] Widget tests for cards and screens

Voice:
- [ ] STT: faster-whisper (local) with Groq Whisper option; Hindi/Hinglish
- [ ] TTS: edge-tts behind a flag + offline fallback (Piper or SAPI)
- [ ] Push-to-talk, global hotkey, barge-in

## Phases 3–10

See spec §14. Break each phase into checklist items here when it starts.

## Needs device test (cannot be verified in the cloud workspace)

- Phase 1 on Windows with a real key: `scripts\dev.ps1`, then "Chrome kholo",
  "notepad kholo", "AI news search karo", "gitm.edu.in kholo". Check that apps
  open, sources are named, and Hindi/Hinglish replies read well.
- Live `ddgs` search and `read_page` against real sites (the workspace blocks
  outbound web requests, so only mocked transports were tested).
- Model IDs in `config/models.yaml` against live Groq/Gemini `/models` lists.

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
