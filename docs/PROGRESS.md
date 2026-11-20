# Rishu — build progress

Checkpoint file. Every session reads this first and updates it with every push.
Rules for sessions are in `CLAUDE.md`.

**Current phase:** Owner priorities of 2026-11-20 (see the next section; they come before the phase order)
**Last updated:** 2026-11-20

## Owner priorities (2026-11-20) — work in this order, before the phase order

The owner tried v0.4.1 and asked (voice call, 20 Nov): Rishu must not refuse
work it does not know; it should ask to be taught once and then do it. Most of
his work is in the browser (college LMS "Lexyta", Google Sheets, Gmail) and in
WhatsApp. Two personas, a small local model for low-end laptops, teacher tools
and the Android app. Voice cloning is on hold. A new installer only when a
group of items is done (not after every step).

P1 — Personas and voice
- [x] Setting `persona`: `professional` (default) and `personal` (warm, caring,
      a little playful, uses the owner's name; still honest that it is an AI,
      nothing sexual, never guilt-trips or discourages time with people).
      Prompts in `shared/prompts/personas/`; picker in Settings (onboarding picker: later).
- [x] Personalisation: how Rishu addresses the user ("Sir", name, …) and a free
      "About me / how to talk to me" text added to the system prompt.
- [x] Natural Indian voice per persona (personal → female Swara/Neerja by
      default, slightly slower and warmer rate); keep the male option.

P2 — Browser control (Chrome DevTools Protocol, no new heavy dependency)
- [x] Start Chrome (or Edge) with remote debugging on Rishu's own profile folder;
      the user signs in to sites once in that window (Rishu never stores passwords).
- [x] Tools: open a page, read the page as a structured outline (headings,
      buttons, fields with labels, tables/lists with row text, each with a ref),
      click, type, select, press keys, wait for text, screenshot to vision.
      Page text is untrusted. Actions on signed-in sites are R2; "submit / lock /
      send / delete" buttons always need explicit approval.
      Done: `rishu_core/browser/` (CDP client, launcher, page control in an
      isolated JS world so page scripts cannot fake labels), tools
      `browser_open/read/click/type/select/press/look`; links R0, small
      changes R1, risky labels R2; password fields are never typed into;
      tested against real headless Chrome (`tests/test_browser.py`).
- [x] R3 step-up (Phase 3 item, needed after reading pages): approval card +
      Rishu PIN + Windows Hello; without both set up R3 stays refused.
      Agent step limit 8 → 20 for website work.

P3 — Teach mode ("sikha do, main seekh loongi")
- [ ] When no tool or skill fits, Rishu offers to learn instead of refusing.
- [ ] Recorder: a script injected into Rishu's Chrome records clicks, typing and
      navigation with robust targets (role + name, label, test id, text); the
      user can speak notes while showing; "bas, ho gaya" stops.
- [ ] Skill = description + steps + parameters (typed values become variables),
      saved encrypted in the data folder; list / rename / delete in the app.
- [ ] Replay with new values (the model fills the parameters), check each step,
      ask when a step fails, "aise nahi, aise karo" re-records that step.

P4 — Lexyta LMS (lms.lexyta.com) — page structure in `docs/lms/lexyta.md`
- [ ] Built-in skill: mark attendance of a class meeting ("roll 5 aur 12
      absent, baaki present"): search/paginate, set each status, then "Mark
      remaining as present"; "Submit & lock attendance" only after approval.
- [ ] Enter assignment / sessional marks — needs the gradebook pages (asked in
      `docs/NEEDS_USER.md`).
- [ ] Check Word submissions: suggest marks within the owner's range with a
      one-line reason; one approval for the whole table, then enter.

P5 — Sheets, Excel, CSV and register photos
- [ ] Read and fill .xlsx/.csv (attendance, marks), fuzzy name matching
      ("Aryan" ↔ "Aryan Kumar", roll numbers), preview table → approval → write.
- [ ] Photo of a handwritten register → vision model → table → match → fill.
- [ ] Google Sheets through the browser tools (P2).

P6 — WhatsApp and email on command
- [ ] WhatsApp Desktop: "Shruti ko bolo aaj nahi aa sakta" → open her chat by
      name, write the message, read it out, send after "haan" (UI automation of
      the official app; no unofficial APIs).
- [ ] Gmail in Rishu's Chrome: read new mail aloud, reply / send after approval.
- [ ] Spoken alert for incoming WhatsApp messages (Windows notifications) — research.

P7 — Small local model (works on low-end laptops, no key, no limit)
- [ ] llama.cpp server (MIT) shipped with Rishu; the smallest capable
      Apache-2.0 instruct model downloaded once on first use; router uses it
      offline or when every free key is exhausted. Model IDs in `config/models.yaml`.

P8 — Teacher mode
- [ ] Weekly timetable, "aaj kaunsi class hai", reminder before each lecture.
- [ ] Notes, quiz, question paper and result sheet as Word/Excel files.

P9 — Android app
- [ ] Talk to Rishu, reminders, open apps, WhatsApp on the phone; send a command
      to the laptop Rishu (LMS and other heavy work run on the laptop).

P10 — Later
- [ ] Dictation into any app, find/open/organise files, PDF/Word summaries,
      morning briefing, meeting notes, LinkedIn drafts, freelancing helpers
      (proposals, invoices, deadlines). Voice cloning: on hold (owner, 20 Nov).

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
- [x] Tests: mock-LLM agent flows, 429 fallback, permissions, tools (77 tests then;
      158 with the Phase 2 server)
- [x] Acceptance with the scripted model: "Chrome kholo" and "AI news search karo"
      (with sources) pass in `core/tests/test_agent.py`
- [ ] Acceptance with a real LLM and a real Windows PC (see "Needs device test")

Phase 1 leftovers to pick up in Phase 2/3:
- (done in Phase 2) API keys: saved keys live in the OS secure store; environment
  variables still work and are used when no key is saved.
- `open_app` indexes Start-menu shortcuts and aliases; Store (UWP) apps without a
  shortcut need `Get-StartApps` support.
- (done in Phase 2) The WebSocket server runs the agent in a worker thread and
  streams tokens.

## Phase 2 — App + Voice (Windows)

Build pipeline (`.github/workflows/build.yml`, Flutter pinned to 3.50.x):
- [x] GitHub Actions: Windows build (Flutter + PyInstaller + Inno Setup) → `RishuSetup-x.y.z.exe`
- [x] GitHub Actions: Android release APK (arm64) with the 30 MB size gate
- [x] Platform folders `app/android` and `app/windows` are in the repo (generated by
      CI with Flutter 3.50.0). App name "Rishu", orb icon (`scripts/make_icons.py`),
      dark launch screen, INTERNET permission, single-instance Windows app.
- [x] Release: pushing a tag `vX.Y.Z` builds both apps and publishes them as a
      GitHub Release (`release` job in `build.yml`; optional notes in
      `docs/release-notes/vX.Y.Z.md`). Not exercised yet: the first tag comes
      when Phase 2 is usable end to end.
- [x] Release APK signing: the workflow uses the keystore from GitHub Secrets when
      it exists, else the debug key. **Owner action pending:** see `docs/NEEDS_USER.md`.

Core server (`core/rishu_core/api/`, started with `rishu-core --serve`):
- [x] FastAPI + WebSocket server implementing `shared/protocol` (agent runs in a
      worker thread; approvals travel as `tool_call_proposed` / `approval_response`
      with a timeout; `stop` cancels the turn and any waiting approval)
- [x] Token streaming from the provider client to `assistant_token` events
      (STOP also interrupts a reply while it is being written)
- [x] Security of the local API: 127.0.0.1 only, session token in the
      `Authorization` header, requests with a browser `Origin` are refused
- [x] HTTP API for the app: settings, provider list, save / delete / test an API key,
      activity log
- [x] API keys in the OS secure store: Windows DPAPI (`security/secrets.py`);
      memory-only fallback elsewhere, and the app is told (`keys_persist`)
- [x] User settings file (name, language, script, autonomy mode, streaming) with
      validation; a change applies to the running conversation
- [x] Contract tests: every event the core sends is checked against the JSON
      schema; `shared/protocol/fixtures.json` is shared with the Dart tests
- [x] `sources` card after `web_search` / `read_page` (title + link of every page
      used; only http(s) links), and `hello` tells the app how long an approval
      card waits (`capabilities.approval_timeout_seconds`)
- [x] The packaged core proves itself: `rishu-core.exe --selftest` starts the
      server and runs a turn over a real WebSocket (runs in the Windows build)
- [x] The Windows app starts the bundled core (`core\rishu-core.exe --serve
      --exit-with-parent`, token in `RISHU_TOKEN`, ready line on stdout and in
      `RISHU_READY_FILE`, parent watched through `RISHU_PARENT_PID`) and connects on
      127.0.0.1. CI installs the built installer and runs one real turn (smoke test).

Flutter app (`app/lib/`, showcase build 2026-11-19):
- [x] App structure with ChangeNotifier state (no Riverpod: zero third-party
      packages keeps the blind CI build safe); dark theme; UI text in Hinglish or
      English following the language setting (simple `tr()`, not full i18n yet)
- [x] Animated orb reacting to state and to the microphone level
- [x] Conversation: streaming text, tool steps, sources card, approval card with
      countdown, notices/errors, read-aloud and copy buttons, typing indicator
- [x] Onboarding: name, language, voice preview, free Groq key Check + Save, offline skip
- [x] Settings: language, voice, autonomy mode, API keys; activity log screen
- [x] STOP while busy/speaking/listening (button, Esc); Ctrl+Space mic; Ctrl+N new chat
- [x] State and widget tests with a fake core (`app/test/widget_test.dart`)
- [ ] Light theme; full i18n tables; Riverpod migration (optional)

Voice (core side, `core/rishu_core/voice/`):
- [x] Microphone capture with silence detection (sounddevice), live `audio_level`
- [x] STT through Groq Whisper (`whisper-large-v3-turbo`, from `config/models.yaml`);
      local faster-whisper is deferred (installer size)
- [x] TTS: edge-tts neural voices (hi-IN / en-IN, male or female, picked by script)
      with Windows SAPI (PowerShell System.Speech) as the offline fallback
- [x] Playback through Windows MCI (winmm), sentence by sentence, STOP and barge-in
- [x] Protocol: `listen_start`, `listen_stop`, `speak`, `audio_level`; `GET /v1/voice`
- [x] Global hotkey Ctrl+Shift+Space (Windows RegisterHotKey in the core) toggles
      listening and brings the window to the front

## Showcase sprint (2026-11-19 night) — beyond the phase order

Published **v0.1.0** (Windows installer). Added for the demo, ahead of their phases:
- [x] Tools: play_youtube, browser_search, whatsapp_draft (official click-to-chat,
      user presses Send, R2), email_draft (mailto, R2)
- [x] Tools: volume (media keys), screenshot (PowerShell), lock_computer (R2),
      battery_status
- [x] Reminders/timers (`set_reminder`, `list_reminders`, `cancel_reminder`),
      delivered as a `reminder` event and spoken aloud (part of Phase 5)
- [x] Memory of facts the user asks to remember (`remember`, `forget`,
      `list_memories`), injected into the system prompt with the current time
      (simple Phase 4 memory; encrypted with DPAPI since v0.4.1)
- [x] Weather from Open-Meteo (free; non-commercial terms: check before a paid product)
- [x] CI: installed-app smoke test on Windows; real-model end-to-end with Ollama
- [x] Screen vision (`look_at_screen`): scaled screenshot to a Groq vision model (v0.3.0)
- [x] Phase 3 start — lock (v0.4.0): PIN (salted scrypt hash, pause after 5
      wrong tries), Windows Hello (fingerprint/face/Windows PIN via
      UserConsentVerifier), spoken password (normalized transcript in the DPAPI
      secret store, fuzzy match; only unlocks, never approves), panic phrase
      "Rishu lock", auto-lock after 10 idle minutes, lock screen in the app;
      while locked the core refuses chat, actions, settings, keys and the
      activity log (HTTP 423), and due reminders are announced without details

- [x] Conversation mode (`follow_up`, off by default, v0.4.0): after a spoken
      reply to a spoken request the mic opens again for 6 s; silence ends it
      quietly; "bas" / "thank you" / "dhanyavaad" end it with a short goodbye;
      typed messages and STOP never re-open the mic
- [x] Spoken hello on launch; clear error when Windows sends only silence
      (microphone privacy switch or a muted mic); speech threshold for quiet
      laptop mics lowered (v0.4.0)

## Phase 3 — Security (remaining)

- [ ] R3 step-up with two factors (PIN + Windows Hello) in the approval card
- [ ] Face unlock with the camera (opt-in; liveness check) — Windows Hello face already works where the PC has an IR camera
- [x] Notes, memory and reminders encrypted at rest with DPAPI (`security/vault.py`; old plain files are read and re-encrypted on the next write; a file from another account is set aside as `.unreadable`)
- [ ] Encrypt the activity log and (later) the conversation history
- [ ] Voice biometrics (speaker verification) on top of the spoken-password transcript

## Phases 4–10

See spec §14. Break each phase into checklist items here when it starts.

## Needs device test (cannot be verified in the cloud workspace)

- Phase 1 on Windows with a real key: `scripts\dev.ps1`, then "Chrome kholo",
  "notepad kholo", "AI news search karo", "gitm.edu.in kholo". Check that apps
  open, sources are named, and Hindi/Hinglish replies read well.
- Token streaming against real Groq / Gemini / Ollama endpoints (tested here
  with recorded SSE shapes only), including a tool call split across chunks.
- Live `ddgs` search and `read_page` against real sites (the workspace blocks
  outbound web requests, so only mocked transports were tested).
- Model IDs in `config/models.yaml` against live Groq/Gemini `/models` lists.
- Lock: Windows Hello dialog on a PC with fingerprint/face/Windows PIN set up
  (on the CI runner the WinRT check answers `unavailable:DeviceNotPresent`, so
  the script loads and runs; the verification dialog itself is untested); spoken
  password with a real mic and Groq Whisper.

## Known issues

- Offline (no internet) Hindi speech needs the Windows Hindi speech pack; without
  it, Devanagari text is not spoken by the offline voice (natural voices online work).
- PyInstaller-built executables are sometimes flagged by antivirus heuristics;
  code signing (paid) and building the bootloader from source would reduce it.
- edge-tts relies on Microsoft's Edge read-aloud service (not an official API):
  it can be switched off in `config/defaults.yaml` (`voice.edge_tts`).

- R3 actions are always refused for now: step-up authentication (two factors)
  arrives with the security module in Phase 3. The app is told through
  `capabilities.step_up = false` and the user gets a clear message.
- "Always allow for this skill" is kept for the running session only; it is
  saved permanently when the skills engine arrives (Phase 6).
- The cloud workspace cannot download workflow artifacts (the storage host is
  blocked), so built installers/APKs can be checked only through CI logs and
  the size gate, not opened here.

## Additions beyond the spec

- Showcase sprint additions listed above (browser shortcuts, drafts, system
  controls, reminders, memory, weather, global hotkey, voice preview).

- Offline intent fallback in the core (Phase 1): basic Hinglish/Hindi/English
  commands still work when no LLM provider is reachable.
- The local API refuses requests that carry a browser `Origin` header, so a web
  page open in the user's browser can never talk to Rishu, even with the token.
- The core exits by itself when the app that started it goes away
  (`--exit-with-parent`), so no background process is left behind after a crash.
- Windows: only one Rishu runs at a time; starting it again brings the open
  window to the front.
- `hello` event and `new_conversation` event in the protocol; `assistant_token`
  can carry `reset` (withdraw a half-written reply).

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
- 2026-11-16: Platform folders were generated on GitHub Actions and committed
  from there (commit by `github-actions[bot]`), because the cloud workspace can
  reach neither the Flutter SDK nor workflow artifacts.
- 2026-11-16: API keys are passed to the core over the local API and stored with
  DPAPI directly (ctypes), not through the `keyring` package: one dependency less
  in the installer. `keyring` is used only on non-Windows development machines
  when it happens to be installed.
- 2026-11-16: No open-source license file yet. The repo is public but the owner
  plans a business; licensing is the owner's decision.
