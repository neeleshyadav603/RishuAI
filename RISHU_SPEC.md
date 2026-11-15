# RISHU — Personal AI Assistant
## Master Build Spec v1.0 (for Claude Code)

- **Owner:** Neelesh — GITM project + future product
- **Date:** 16 Nov 2026
- **Targets:** Android (single APK) + Windows desktop app (.exe installer)
- **Budget:** ₹0 for development (the only optional cost: $25 one-time Google Play account, later)

---

### Neelesh के लिए (कैसे use करें)
1. एक खाली folder बनाओ, जैसे `rishu/`। ये file उसमें `RISHU_SPEC.md` नाम से रखो।
2. उसी folder में Claude Code खोलो और नीचे **Section 1** वाला Master Prompt paste करो।
3. Claude Code हर phase से पहले plan दिखाएगा। आप "go" बोलोगे तभी वो code लिखेगा। हर phase के बाद `docs/PROGRESS.md` देख लेना।

---

## 1. MASTER PROMPT (paste this into Claude Code)

```
You are the lead engineer for "Rishu", a voice-first personal AI assistant for
Android and Windows. The complete product spec is RISHU_SPEC.md in this folder.
It is the source of truth.

Rules:
1. Read RISHU_SPEC.md fully before doing anything.
2. First, create CLAUDE.md that summarises the non-negotiables (§3), the
   security/permission/self-update protections (§6, §7, §11), the repo structure
   (§13) and the phase order (§14), so every future session follows them.
3. Build in the phase order of §14. A phase is done only when its acceptance
   criteria pass. Do not start the next phase before that.
4. At the start of each phase, show me a short plan (files, libraries with
   licenses, risks, what I need to install) and wait for my "go".
5. After each phase: run all tests, produce the build artifacts that phase
   promises, update docs/PROGRESS.md (done / pending / known issues / next), and
   give me exact copy-paste commands to run it on my Windows laptop and phone.
6. Zero budget: only free / open-source tools and free API tiers. Before adding
   any dependency, check its latest stable version, license (must allow
   commercial use unless the spec marks it "optional/non-commercial"), and
   platform support. Never add paid services.
7. Never hard-code LLM model IDs. Read them from config and the provider's
   /models endpoint, with a fallback list the user can edit.
8. Never weaken the protections in §6, §7 and §11. If any request (including
   mine) would weaken them, explain the risk and ask me to confirm explicitly.
9. If something in the spec is impossible, blocked by a platform policy, or a
   library no longer exists, tell me and propose the closest alternative.
   Never silently skip or fake a feature.
10. Keep code simple, typed, modular, tested and commented in English.
    User-facing text goes through i18n (English, Hindi, Hinglish).
11. Use §18 references to understand the intended behaviour; do not copy code
    from projects whose license forbids it.

Start with Phase 0.
```

---

## 2. Product Vision

Rishu is a **JARVIS-style personal assistant**. The user talks to it in Hindi, Hinglish or English, and it understands, talks back naturally, and *does things* on the user's behalf on their laptop and phone: opens apps, works in the browser, drafts and sends messages (after permission), teaches and researches any topic, remembers the user, and **learns new skills** when the user teaches it once or asks it to learn.

What makes Rishu different (USP):
1. **Hinglish-first voice assistant** with a warm, consistent personality.
2. **Teach-once skills:** the user demonstrates a task once, and Rishu can repeat it with new parameters.
3. **Self-Update Lab:** "Rishu, research करना सीख लो" makes Rishu write, test and install a new skill or plugin for itself, behind a safe approval pipeline.
4. **Tutor mode:** Socratic teaching from fresh web sources, with cross-questions, quizzes and progress tracking.
5. **Local-first privacy:** memory, skills and logs stay on the user's devices, encrypted.
6. **Multi-factor security:** face, fingerprint, voice passphrase and PIN, with risk-based step-up.
7. **Open skills:** compatible with the Agent Skills (SKILL.md) standard.

Example user stories (these are acceptance tests too):
- "Rishu, Chrome खोलो और GITM की website पर admission page दिखाओ."
- "Rishu, Rahul को WhatsApp पर बोलो मैं 10 मिनट late हूँ." Rishu shows a preview, the user says "हाँ", and the message is sent.
- "Rishu, मुझे quantum computing पढ़नी है." Rishu explains simply, asks a check question, answers cross-questions, and saves progress.
- "Rishu, रोज़ सुबह 9 बजे AI पर एक LinkedIn post का draft बनाओ." Rishu researches, drafts, shows it, and opens LinkedIn with the text after approval.
- "Rishu, ये सीखो" (teach mode): the user records a task once, and Rishu turns it into a reusable skill.
- "Rishu, PDF summarise करना सीख लो" (self-update): plan → code → tests → review → approval → new version.
- "Rishu lock": immediate lock. "Rishu, पुराना version लाओ": rollback.

---

## 3. Non-Negotiables

1. **Zero budget.** Free/open-source only. LLMs via free tiers with **BYOK** (each user brings their own free API key), plus local models via Ollama on desktop.
2. **Local-first.** Phone actions run locally through Android intents and services, not cloud APIs. Desktop actions run locally. No unofficial reverse-engineered APIs.
3. **Permission-first.** Risk-based confirmation for every action (§7). Rishu never completes payments.
4. **Privacy.** All personal data is stored locally and encrypted, with telemetry off by default. Users can see, edit, export and delete everything.
5. **Platforms:**
   - Android: a **single APK**, release `arm64-v8a` **≤ 30 MB**, with no bundled ML models (models download on demand).
   - Windows 10/11: a **single installer `RishuSetup-x.y.z.exe`** (per-user, no admin rights needed).
6. **Simplicity.** A non-technical user must be able to install, set up and use Rishu in under 10 minutes using the onboarding wizard.
7. **Honest persona.** Rishu is warm, but never claims to be human or to be a real person, even when it uses a custom voice.
8. **Graceful degradation.** If the internet, an API quota or a model is unavailable, Rishu says so clearly and falls back (local model, offline commands, text mode).
9. **Compliance** with the platform and legal notes in §17.

---

## 4. Architecture

```
                    ┌──────────────────────────────────────────┐
                    │        Rishu App (Flutter, one codebase)  │
                    │  UI: orb, chat, cards, tutor, skills,     │
                    │  memory, log, lab, devices, settings      │
                    └───────────────┬───────────────┬──────────┘
                     Windows build  │               │ Android build (single APK)
                                    │               │
             ws://127.0.0.1 (token) │               │ in-process
                                    ▼               ▼
┌───────────────────────────────────────────┐   ┌──────────────────────────────────┐
│  rishu-core (Python, FastAPI + WebSocket) │   │  mobile_core (Dart, in the APK)   │
│  - Agent loop + planner + tool registry   │◄─►│  - Agent loop (same protocol)     │
│  - LLM router (Groq/Gemini/Ollama/...)    │LAN│  - LLM router (HTTP providers)    │
│  - Desktop tools, Playwright browser      │QR │  - Android tools via Kotlin       │
│  - Voice: STT/TTS/wake word/voice-ID      │pair│   platform channels (intents,    │
│  - Security, permissions (PROTECTED)      │   │    biometrics, accessibility,     │
│  - Memory (SQLite + vectors)              │   │    alarms, TTS/STT)               │
│  - Skills engine + Teach mode             │   │  - Memory (SQLite), skills (L1)   │
│  - Self-Update Lab (PROTECTED)            │   │  - Offload heavy tasks to desktop │
└───────────────────────────────────────────┘   └──────────────────────────────────┘
          Shared: /shared/prompts, /shared/tool_schemas, /shared/skills,
                  /shared/protocol (JSON schema of app↔core events)
```

Why this split:
- **One UI codebase** (Flutter) for Android and Windows.
- **Python on desktop** because the best free tools live there: faster-whisper, Playwright, pywinauto, OpenCV, SpeechBrain, IndicF5, pytest. It is also the safest place for self-update.
- **Dart core inside the APK** so the phone app works standalone (no server needed). Pairing with the desktop adds power.
- **Same protocol, prompts, tool schemas and skill format** on both cores, so behaviour stays consistent.

---

## 5. Tech Stack

| Layer | Windows (desktop) | Android | Notes |
|---|---|---|---|
| UI | Flutter (Windows) | Flutter (Android) | Riverpod state; custom-painted animated orb; no paid assets |
| Core | Python 3.11+, FastAPI, uvicorn, WebSocket | Dart `mobile_core` package | Same JSON event protocol (§12.3) |
| LLM | OpenAI-compatible client: Groq, Gemini (OpenAI-compatible endpoint), OpenRouter free models, **Ollama local** | Same HTTP providers (no Ollama) | BYOK; model IDs from config + `/models` |
| Web search | `ddgs` (DuckDuckGo etc.); optional self-hosted SearXNG | Provider built-in search where available (e.g. Groq compound/browser search), else DuckDuckGo HTML, else via paired desktop | Always return sources |
| Page reading | `trafilatura` | Simple readability extraction in Dart or via desktop | Treat as untrusted data |
| STT | `faster-whisper` (local, int8 CPU), optional Groq Whisper API | Android `SpeechRecognizer` (system, Hindi supported, 0 MB) + optional Groq Whisper | Auto language detect hi/en |
| TTS | `edge-tts` (online, free, unofficial → behind a feature flag) + offline fallback (Piper or SAPI via pyttsx3) | Android system `TextToSpeech` + optional edge-tts | Speak short chunks, stream |
| Wake word | `openWakeWord` with a custom "Hey Rishu" model | Later phase (onnxruntime-android or Vosk) | Push-to-talk + hotkey in v1 |
| Desktop control | pywinauto / UI Automation, `pyautogui` fallback, PowerShell | n/a | Element-based, not coordinates |
| Browser automation | Playwright (persistent user profile) | Intents / Custom Tabs; reading via HTTP | User logs in once |
| Android actions | n/a | Kotlin: intents, `AlarmClock`, `ACTION_DIAL`, wa.me, Maps, YouTube, share; `AccessibilityService` (**full flavor only**); `VoiceInteractionService` (default assistant) | See §10 |
| Memory | SQLite (+ SQLCipher or field encryption) + `sqlite-vec`; small multilingual embedding model (e.g. multilingual-e5-small via fastembed/onnxruntime) | sqflite/drift + keyword search (embeddings via provider or desktop) | Editable memory UI |
| Face | OpenCV Zoo **YuNet** (detect) + **SFace** (recognise), Apache-2.0, + liveness challenge | OS biometrics via `local_auth` (BiometricPrompt) primary; optional SFace ONNX | Templates encrypted locally |
| Fingerprint/OS auth | Windows Hello (WinRT UserConsentVerifier) | BiometricPrompt | |
| Voice ID | SpeechBrain ECAPA speaker verification (Apache-2.0) | Passphrase only in v1 | Never sufficient alone for R3 |
| OCR / vision | RapidOCR (offline) + vision-capable LLM (free tier) | Vision LLM via API | "Screen par kya hai?" |
| Scheduler | APScheduler + Windows toast notifications | AlarmManager / WorkManager | Reminders, routines |
| Secrets | Windows DPAPI / `keyring` | Android Keystore + encrypted storage | API keys never in plain text |
| Self-update | git (system git or dulwich), venv sandbox, pytest, ruff, bandit | L1 skills sync; APK rebuilt by desktop lab (optional) | §11 |
| Packaging | PyInstaller (onedir) + Flutter Windows release → **Inno Setup** installer | `flutter build apk --release --split-per-abi`, R8 shrink | §16 |

---

## 6. Security & Access (PROTECTED module)

**Unlock methods** (the user picks any combination during onboarding; PIN is mandatory as a fallback):
1. **PIN / password:** Argon2id hash, rate-limited attempts, lockout after repeated failures.
2. **Face unlock:**
   - Desktop: webcam with YuNet + SFace, plus a liveness challenge (blink or turn head on a random prompt) to stop photo/video spoofing.
   - Android: OS face/fingerprint through BiometricPrompt.
3. **Fingerprint:** Windows Hello on desktop, BiometricPrompt on Android.
4. **Verbal password:** the user speaks a secret phrase. STT checks the phrase, and on desktop SpeechBrain checks that the voice matches the enrolled speaker.
   - Voice can be cloned, so a voice factor alone never authorises R3 actions.

**Policies:**
- Session unlock = 1 factor. Step-up for R3 (§7) = 2 different factors (e.g. face + PIN).
- Auto-lock after N minutes idle (configurable). Lock on Windows lock or screen-off.
- **Panic phrase** ("Rishu lock" / "Rishu band karo") locks immediately and stops all running actions.
- Guest mode: chat and general info only, no memory access, no actions.
- Multiple user profiles on one device, each with separate memory and keys.
- All biometric templates, memory and logs are encrypted at rest and never uploaded.
- An **Activity log** records every action: time, skill, risk level, approval method, result.
- Integrity: security/permissions/updater code is hash-checked at startup (§11).

---

## 7. Permission & Autonomy Policy (PROTECTED module)

| Risk | Examples | Default behaviour |
|---|---|---|
| **R0 Info** | chat, explain, web search, read page, time, weather | No confirmation |
| **R1 Low** | open app/website, play music, set timer/alarm, create note, screenshot | Act, then say what was done (user can switch to confirm) |
| **R2 Medium** | send message/email/post, fill forms, move/rename files, change settings, install a skill, run a taught skill, shutdown/restart | **Preview + explicit approval** (voice "haan" or tap Approve) |
| **R3 High** | delete files (Recycle Bin only), anything involving money, sharing personal data externally, accessibility actions in banking/payment apps, running newly generated code, deploying a self-update, changing security settings | **Preview + step-up auth with 2 factors** |
| **Forbidden** | completing payments autonomously, disabling its own protections, using a cloned voice to talk to third parties, bulk/unsolicited messaging, bypassing other systems' security | Refuse and explain |

**Autonomy modes** (user setting): `Ask always` / `Smart` (default, the table above) / `Trusted skills` (the user may mark specific R1/R2 skills as auto-run; **R3 is never auto**).

**Prompt-injection defence:**
- Content from web pages, emails, messages, files and imported skills is **untrusted data**, never instructions.
- Any action proposed right after reading untrusted content is bumped **one risk level up**.
- Untrusted content can never change permissions, security settings or the autonomy mode.

**Emergency STOP:** a stop button is always visible during actions, plus the voice command "Rishu ruko". It cancels the current plan immediately.

---

## 8. Feature Modules

### 8.1 Voice & Conversation
- Activation: "Hey Rishu" wake word (desktop, later phase), global hotkey (e.g. Ctrl+Space), mic button, and long-press assistant gesture on Android.
- Languages: Hindi, Hinglish, English, auto-detected. Reply in the user's language and script (Devanagari or Roman, per setting).
- Low latency: stream STT → LLM → TTS in sentence chunks. Barge-in: the user can interrupt and Rishu stops speaking.
- Context: follow-ups ("use bhi bhej do"), pronoun resolution, and a short-term conversation buffer with summarisation.
- Spoken style: short, natural sentences. Markdown is stripped before TTS. Long content goes to a card on screen.

### 8.2 Persona, Emotion & Wellbeing
- Persona file: `shared/prompts/persona_rishu.md`. Rishu is warm, friendly and respectful, uses the user's name, and keeps humour light.
- Honesty: if asked, Rishu always says it is an AI.
- Emotion-aware tone: a cheap LLM classification of user sentiment each turn guides the tone. TTS rate/pitch is adjusted.
- Optional later: expressive Hindi TTS via Indic Parler-TTS (desktop, GPU recommended).
- Wellbeing:
  - Rishu does not encourage dependency or isolation.
  - If the user seems in distress, it responds with care and suggests talking to trusted people or a professional. India helpline: Tele-MANAS 14416.

### 8.3 Desktop Control (Windows)
- **Apps:** open, close or switch by name. Index the Start menu and installed apps; fuzzy-match Hindi/English names.
- **Windows:** minimise, maximise, snap, focus.
- **Files:**
  - search (Windows Search index first, bounded walk as fallback), open
  - move/rename = R2
  - delete = R3, Recycle Bin only
- **System:**
  - volume/mute, brightness, Wi-Fi/Bluetooth (where APIs allow), battery, lock
  - sleep/shutdown/restart = R2
- Screenshot, clipboard read/write, dictation (type into the focused field).

### 8.4 Browser & Web
- Playwright with a persistent profile: open sites, search, click, fill forms (R2), download, read and summarise pages.
- YouTube: search and play.
- Shopping: compare prices; never buy (R3, hand-over only).
- Gmail: open compose with a draft; reading via a logged-in browser session (later phase).

### 8.5 Communication
- **WhatsApp:** use the official click-to-chat deep link `https://wa.me/<number>?text=<msg>`.
  - Desktop: opens WhatsApp Desktop/Web with the message pre-filled. After approval, a taught UIA skill may press Send.
  - Android: wa.me intent. After approval, the full flavor may tap Send via accessibility.
  - **No unofficial WhatsApp libraries** (whatsapp-web.js, Baileys, etc.): they carry ban risk and violate WhatsApp's terms.
- **Contacts:** a local contact book that the user manages (name, aliases, phone, email), synced between devices.
- **Calls:** `tel:` intent on Android. The desktop can hand a call off to the paired phone.
- **Email:** mailto/Gmail compose draft, with approval before send.
- **LinkedIn:**
  1. Rishu researches and drafts the post.
  2. The user approves.
  3. Rishu opens the LinkedIn composer with the text, and **the user presses Post**. No automated posting bots (against LinkedIn terms). The official API is an optional later route.

### 8.6 Tutor Mode ("Rishu, mujhe X padhna hai")
- Ask level and goal (school / B.Tech / researcher), then build a mini-syllabus.
- Research fresh sources (§8.7), then explain in short chunks in the user's language, with examples, pros/cons, and diagrams (Mermaid rendered in the UI).
- **Socratic loop:** after every 2–3 chunks, ask a check question. Handle cross-questions. Detect misconceptions and re-explain differently.
- Quizzes (MCQ + short answer), flashcards with spaced repetition, and notes export (Markdown/PDF).
- Learner profile per topic: level, covered sub-topics, weak areas, next step. "Kal wahi se continue karo" must work.
- Can read the user's own PDF/notes and teach from them.
- Always cite sources for factual claims.

### 8.7 Research Mode
- Pipeline:
  1. plan sub-questions
  2. multiple searches
  3. fetch and extract pages
  4. cross-check claims
  5. synthesise with citations
- Output: a spoken summary, a saved report (Markdown), and an optional conversion into a LinkedIn post, notes or slides outline.

### 8.8 Productivity & Routines
- Reminders, alarms, timers, to-dos, a local calendar, and notes.
- Daily briefing: schedule, weather (Open-Meteo, free, no key), news headlines (RSS), and pending tasks.
- **Routines:**
  - "Good morning Rishu" runs a briefing, opens apps and plays music.
  - Time-based and event-based triggers (battery low, connected to home Wi-Fi, etc.).
- Focus timer (Pomodoro).
- Meeting notes: record, transcribe and summarise, with a consent reminder.

### 8.9 Memory & Personalization
- Types:
  - **profile** (name, preferences)
  - **people** (relationships, contact aliases)
  - **episodic** (past conversations, vector-searchable)
  - **corrections** ("aise nahi, aise karo")
  - **routines/habits**
- The Memory screen lets the user view, edit, delete, "Rishu, ye bhool jao", "sab bhool jao", export and import memory.
- Memory is used only when relevant. Sensitive memories (health, finance) are never raised unprompted.

### 8.10 Skills Engine (Agent Skills compatible)
- Format: **Agent Skills / SKILL.md** (YAML frontmatter `name`, `description`, optional `allowed-tools`, risk level), plus optional `scripts/`, `references/` and `assets/`.
- Progressive disclosure: only names and descriptions go in the system prompt. Rishu loads the full SKILL.md via a `load_skill` tool when a request matches.
- Skill sources: **bundled** (`shared/skills/`), **taught** (§8.11), **self-created** (§11), and **imported** (GitHub URL or zip).
- **Import safety:**
  - Static scan (dangerous calls, network, file deletion, obfuscation) and license check.
  - Show the SKILL.md and scripts to the user in plain language, enforce `allowed-tools`, and run scripts only in the sandbox.
  - Installing a skill = R2; a skill with scripts = R3.
- Tool mapping: skills written for other agents may reference tools Rishu doesn't have. The importer maps them to Rishu equivalents or flags them.
- Android runs instruction-only skills (L1) using built-in tools. Script skills run on the desktop core, or via the paired desktop.
- **Reflection:** after a successful multi-step task, Rishu may propose "Is kaam ki skill bana loon?" and drafts a skill for review. It never auto-installs.

### 8.11 Teach Mode ("Rishu, ye seekho")
- **Desktop recorder:**
  - Overlay "Recording…". Captures the active app, the UI Automation element for each click (name, control type, automation id), keystrokes (password fields are never recorded), and a screenshot per step.
  - The user may narrate while recording.
- **Compile:** the LLM converts the recording into a parameterised skill (detects variables such as contact name and message text) and shows the steps for review.
- **Test replay:** Rishu replays the skill with test values before saving.
- **Replay engine:**
  - Targets elements, not coordinates (coordinates are the last fallback).
  - Verifies the expected state after each step (UIA check or screenshot).
  - On a mismatch, uses a vision LLM to re-locate the element, or asks the user.
  - Respects risk levels.
- **Browser teach:** records Playwright selectors.
- **Android teach (full flavor):** records accessibility node ids/text; replays via accessibility actions with confirmation.
- **Corrections:** "galat kiya" opens step editing, and the fix is saved to the skill.

### 8.12 Vision
- "Screen par kya hai, samjhao": screenshot → vision LLM explanation.
- OCR on images and documents (RapidOCR offline).
- Later: camera object recognition.

### 8.13 Custom Voice (optional desktop module)
- **IndicF5** (AI4Bharat, MIT) zero-shot voice cloning from a 5–10 s reference clip + transcript. A GPU is recommended; CPU is slow.
- **Consent flow is mandatory:**
  1. The voice owner records a spoken consent statement and the reference clips, and signs a consent record (name, date, purpose).
  2. The consent record is stored with the voice profile.
  3. The owner can revoke it, and revocation deletes the voice profile.
- Cloned voices are used **only for Rishu's own speech to the user**: never for outbound calls, voice notes or messages to others.
- Show an "AI voice" label in the UI and in any exported audio.

### 8.14 Multi-Device
- The desktop is the hub. Pairing:
  1. The desktop shows a QR code (LAN IP + one-time token + certificate fingerprint).
  2. The phone scans it.
  3. The connection uses an encrypted WebSocket with a pinned certificate.
- The paired phone can:
  - use the desktop brain and tools ("laptop pe PPT kholo")
  - receive desktop notifications
  - sync memory, skills and contacts (last-write-wins with timestamps)
- Remote access outside home Wi-Fi: document an optional Tailscale setup (free personal plan). It is not required.
- **Offline mode:** without internet, run basic commands (open apps, alarms, timers, notes) and use a local model if one is installed.

### 8.15 Everyday Utilities
- Weather, news, music (YouTube/Spotify via URL/intents, local files), translation, calculator, unit conversion, jokes, and quick facts with sources.

### 8.16 Business-Ready Hooks (build the flags, keep them OFF)
- Feature flags for premium tiers.
- An ad slot only on non-conversation screens (never inside voice or chat).
- Opt-in anonymous telemetry, an update channel, and an optional user account.

---

## 9. LLM Layer

- **Provider adapters:** a single OpenAI-compatible interface (chat, tools, streaming, vision).
  - Providers: Groq, Gemini (OpenAI-compatible endpoint), OpenRouter (free models), Ollama (desktop local).
  - Users paste their own API keys in onboarding, with a step-by-step guide and a "Test" button.
- **Router:** chooses a model per task type, all configurable in `config/models.yaml`:
  - `fast` for intent and chit-chat
  - `smart` for planning, tutoring and research
  - `coder` for the Self-Update Lab
  - `vision` for screenshots
- **Model IDs:** fetch the `/models` list at startup and on demand. Never hard-code deprecated IDs.
- **Quota handling:** on HTTP 429 or quota errors, fall back to the next provider, then to the local model, and tell the user in one short sentence.
- **Privacy note in onboarding:** some free tiers may use request data to improve the provider's products. Offer Ollama local mode for sensitive use.
- **Agent loop:**
  1. system prompt (persona + rules + skill index + relevant memory)
  2. LLM
  3. tool calls
  4. permission check (§7)
  5. execute
  6. results back to the LLM, until done or max steps (configurable)
  - Stream progress events to the UI.
- **Prompts:** live in `shared/prompts/*.md` (persona, system rules, tutor, research, teach-compiler, skill-writer, self-update-planner, safety). They are versioned and tested with golden conversations.

---

## 10. Android Specifics

- **Build flavors:**
  - `full` — sideloaded APK. Includes the AccessibilityService for in-app actions and teach mode.
  - `play` — no automation AccessibilityService, for a future Play Store listing. Google Play prohibits Accessibility API use that lets an app autonomously initiate, plan and execute actions.
- **Size budget:** release `arm64-v8a` APK ≤ 30 MB.
  - Use `--split-per-abi`, R8/ProGuard, and no bundled models/fonts beyond essentials.
  - Models, voices and wake-word files download on demand with checksum verification.
- **Default assistant:** implement a `VoiceInteractionService` (and handle `ACTION_ASSIST`) so the user can set Rishu as the default digital assistant (long-press power/home).
- **Local actions via intents, no APIs:**
  - open any installed app by name (launcher intent)
  - Maps navigation, dial, alarms/timers (`AlarmClock`)
  - wa.me chat, YouTube search, share sheet, settings pages, camera, web URLs
- **Background listening** (later phase): a foreground service with a persistent notification. Battery-aware; the user can turn it off.
- **Permissions:** request at runtime with a plain-language reason for each (mic, contacts optional, notifications, accessibility for the full flavor).
- **Distribution:** Google is rolling out mandatory developer verification for sideloaded apps (global rollout planned for 2027).
  - Plan to register the app in the Android Developer Console (free limited-distribution accounts exist for students/hobbyists).
  - Document the "advanced flow" install path for testers.

---

## 11. Self-Update Lab (PROTECTED module)

Goal: the user says "Rishu, X seekh lo / ye feature bana lo", and Rishu extends itself safely.

**Levels:**
- **L1 Skill:** new SKILL.md, plus optional scripts, built from existing tools. Most requests should be solved here.
- **L2 Plugin:** a new Python tool module in `core/plugins/<name>/` with a manifest (name, tools, risk levels, permissions, dependencies).
- **L3 Core change:** modifies Rishu's own non-protected code. This creates a new version. It is rare and needs the strictest review.

**Pipeline (every update):**
1. **Understand & plan.** Rishu restates the request, chooses a level, and lists the files, tools, dependencies and risks. The user approves the plan (R2).
2. **Sandbox build.** Rishu creates a git branch/worktree `update/<id>` with a separate venv.
   - Generated code runs in a subprocess with a timeout.
   - Network is restricted to package installs from PyPI during build.
   - There is no access to user data folders.
3. **Test.** Rishu writes unit tests for the new code. All must pass:
   - the new tests
   - the existing test suite
   - the **golden regression suite** (protected)
   - lint (ruff) + security scan (bandit + custom rules: no file deletion outside the sandbox, no exfiltration, no permission changes)
4. **Demo.** Rishu runs one real sample task in the sandbox and shows the result.
5. **Review.** Rishu shows a plain-language summary (Hinglish) plus the diff in a DiffReviewCard.
6. **Approve.** Step-up auth with 2 factors (R3).
7. **Deploy.** Merge, tag a version (`vX.Y.Z`), update `CHANGELOG.md`, hot-reload L1/L2, restart for L3.
8. **Health check.** After deploy, run a smoke test. On failure, **auto-rollback** to the previous tag and report.
9. **Rollback** any time: "Rishu, purana version lao" or the Lab screen.

**Protected paths** (Rishu's file tools and the updater can never write to them):
- `core/rishu_core/security/`
- `core/rishu_core/permissions/`
- `core/rishu_core/updater/`
- `tests/golden/`
- `config/policy.yaml`

Enforcement:
- A path write-guard in the file tools.
- A **hash manifest** of protected files, signed with a key derived from the user's PIN, verified at every startup. If verification fails, Rishu enters safe mode.

**Quality rules:**
- Use the strongest available `coder` model with a maximum iteration count.
- If an update can't pass the tests, Rishu says honestly: "Ye main abhi nahi seekh paaya" and explains why.

**Android:**
- L1 skills sync from the desktop.
- For L2/L3 (Android code), the desktop lab can modify the Flutter app, run `flutter build apk` (if the Flutter SDK is installed), and offer the new APK over LAN/QR. The user installs it manually.
- The APK cannot modify its own compiled code.

---

## 12. Frontend / UX Spec (interactive)

### 12.1 Design principles
- Simple first. Big touch targets. Every screen is usable by voice or by touch/mouse.
- Dark and light themes; Hindi and English UI (i18n); font scaling; screen-reader labels.
- The **animated orb** shows state: idle / listening / thinking / speaking / acting / locked / offline.
- The STOP button is always visible while an action runs.

### 12.2 Screens
1. **Onboarding wizard:**
   - language, name, persona voice
   - LLM provider + API key (guided, with a Test button), optional Ollama detection
   - security setup (PIN mandatory + face/fingerprint/voice passphrase optional)
   - permissions explained, autonomy mode
2. **Lock screen:** face / fingerprint / voice passphrase / PIN.
3. **Home:** orb, big mic button, quick chips (Padhai, Research, Message, Routine, Teach), recent items.
4. **Conversation:** transcript with rich cards:
   - `SourcesCard`, `ActionConfirmCard` (exact preview + Approve / Deny / Always allow for this skill)
   - `ProgressCard` (live multi-step plan with cancel), `QuizCard`, `FlashcardCard`
   - `NotesCard`, `DiffReviewCard`, `ErrorCard` (clear reason + what to do)
5. **Tutor:** topics, progress, weak areas, quizzes, flashcards, continue button.
6. **Skills library:** bundled/taught/imported/self-created; enable/disable, risk level, edit, delete.
7. **Teach mode:** record/stop, step list editor, test replay.
8. **Memory:** searchable list; edit/delete; forget all; export.
9. **Activity log:** filter by date/skill/risk; undo where possible.
10. **Lab (Self-Update):** proposed updates, test results, versions, rollback.
11. **Devices:** pair via QR, paired devices, sync status.
12. **Settings:** voice and language, providers/models, autonomy, security, privacy (export/delete all data), custom voice (with consent), about/version.

### 12.3 App ↔ Core protocol (`shared/protocol/`)
- WebSocket JSON events with a `v` (protocol version) field:
  - `user_message`, `audio_chunk`, `transcript_partial`, `transcript_final`
  - `assistant_token`, `assistant_message`, `card`
  - `tool_call_proposed` (needs approval), `approval_response`, `auth_required`, `auth_result`
  - `tool_progress`, `tool_result`, `state_change`, `stop`, `error`
- Maintain a JSON Schema for every event, plus contract tests on both the Dart and Python sides.

---

## 13. Repository Structure

```
rishu/
├─ RISHU_SPEC.md              # this file (source of truth)
├─ CLAUDE.md                  # rules summary for Claude Code
├─ docs/  PROGRESS.md  ARCHITECTURE.md  SETUP_WINDOWS.md  SETUP_ANDROID.md  USER_GUIDE.md  GITM_REPORT/
├─ config/  models.yaml  policy.yaml(PROTECTED)  defaults.yaml
├─ shared/
│  ├─ prompts/      persona_rishu.md  system_rules.md  tutor.md  research.md  teach_compiler.md  skill_writer.md  update_planner.md
│  ├─ tool_schemas/ *.json
│  ├─ protocol/     events.schema.json
│  └─ skills/       <bundled skills as SKILL.md folders>
├─ core/                       # Python desktop core
│  ├─ rishu_core/
│  │  ├─ api/  agent/  llm/  tools/{desktop,browser,web,comms,system,files,productivity}/
│  │  ├─ skills/  teach/  memory/  voice/{stt,tts,wakeword,voiceid,voiceclone}/
│  │  ├─ tutor/  research/  vision/  sync/  scheduler/
│  │  ├─ security/     (PROTECTED)
│  │  ├─ permissions/  (PROTECTED)
│  │  └─ updater/      (PROTECTED)
│  ├─ plugins/                 # L2 plugins (self-created or installed)
│  └─ tests/  unit/  integration/  golden/(PROTECTED)
├─ app/                        # Flutter app (Android + Windows)
│  ├─ lib/  ui/  state/  core_client/  mobile_core/  i18n/
│  ├─ android/  (Kotlin: intents, accessibility, assistant service, biometrics bridge)
│  └─ windows/
├─ installer/  rishu.iss       # Inno Setup script
└─ scripts/    dev.ps1  build_windows.ps1  build_android.ps1  test_all.ps1
```

---

## 14. Phased Roadmap (with acceptance criteria)

| Phase | Scope | Acceptance criteria |
|---|---|---|
| **0 Setup** | Repo, CLAUDE.md, config, shared schemas, protocol, scripts, PROGRESS.md | `test_all.ps1` runs (empty suites pass); `dev.ps1` starts core + app skeleton |
| **1 Brain (desktop core)** | LLM adapters + router + quota fallback; agent loop; tools: open_app, open_url, web_search, read_page, time, notes; basic permission engine; CLI/text chat | "Chrome kholo", "AI news search karo (with sources)" work in text; mock-LLM tests pass; 429 fallback tested |
| **2 App + Voice (Windows)** | Flutter Windows UI (home, orb, conversation, cards, settings); WebSocket client; STT (faster-whisper + Groq option), TTS (edge-tts + offline fallback); push-to-talk + hotkey; barge-in; Hindi/Hinglish | Voice round-trip in Hindi; ActionConfirmCard works; STOP cancels; first audio reply target < 3 s on Groq |
| **3 Security** | PIN, face (YuNet+SFace+liveness), Windows Hello, voice passphrase + SpeechBrain; risk levels R0–R3 + step-up; auto-lock; panic phrase; encrypted storage; activity log | Photo spoof fails liveness; R3 needs 2 factors; "Rishu lock" locks instantly; data unreadable without unlock |
| **4 Memory + Tutor + Research** | Memory store + UI; tutor mode with Socratic loop, quiz, flashcards, progress; research pipeline with citations and saved reports | "Quantum computing padhao" full session incl. cross-questions + quiz + resume next day; memory edit/forget works |
| **5 Browser + Comms + Productivity** | Playwright tools; WhatsApp via wa.me; contacts; email draft; LinkedIn draft→composer; reminders, alarms, routines, daily briefing, toasts | Rahul message story passes with preview; "Good morning Rishu" routine runs; reminder fires |
| **6 Skills + Teach** | Skills engine (SKILL.md, progressive loading, allowed-tools); GitHub import + scanner; teach recorder → compiler → replay; corrections; reflection proposals | Import a public research skill and use it; teach "open X and do Y" once and replay with new parameters |
| **7 Android APK** | Flutter Android; mobile_core (Dart agent loop); Android STT/TTS; intents; BiometricPrompt; default assistant; QR pairing + sync; offline basics; flavors full/play; accessibility (full) | Single arm64 APK ≤ 30 MB installs and works standalone (open Maps, set alarm, wa.me message, tutor chat); pairing controls the laptop |
| **8 Self-Update Lab** | L1/L2/L3 pipeline, sandbox, tests, review card, 2FA deploy, versioning, health check, auto-rollback, protected-path guard + signed hash manifest; optional APK rebuild | "PDF summarise karna seekh lo" produces a working, tested, approved plugin; a deliberately broken update auto-rolls back; writes to protected paths are blocked |
| **9 Extras** | "Hey Rishu" wake word (desktop), vision + OCR, emotion-aware tone, custom voice (IndicF5) with consent flow, Android background listening | Wake word false-accepts rare in a quiet room; consent required before any clone; "AI voice" label shown |
| **10 Ship** | Windows installer (Inno Setup), signed release APK, onboarding polish, USER_GUIDE, GITM report pack, demo script | Fresh Windows PC: install → onboarding → first command < 10 min; APK fresh install same; all tests green |

---

## 15. Testing & Quality

- **Python:** pytest
  - unit tests per tool, using fakes for OS/browser
  - a **mock LLM** that replays scripted tool calls
  - golden Hinglish conversations in `tests/golden` (protected)
- **Flutter:** widget tests for cards and screens; integration test app↔core over WebSocket; protocol contract tests.
- **Security tests:** spoof attempts (photo for face, recorded audio for voice), R3 without step-up, prompt-injection pages that try to trigger actions, writes to protected paths.
- **Performance targets** (measure and report in PROGRESS.md):
  - core idle RAM < 400 MB without local models
  - app cold start < 5 s
  - APK ≤ 30 MB
- **Manual QA checklist** per phase in `docs/QA.md`.

---

## 16. Packaging & Distribution (₹0)

- **Windows:**
  - PyInstaller (onedir) for the core + Flutter Windows release, packaged by **Inno Setup** into `RishuSetup-x.y.z.exe`.
  - Per-user install, Start-menu shortcut, optional autostart, tray icon, uninstaller.
  - Models download to `%LOCALAPPDATA%\Rishu\models` with a progress bar and checksums.
  - Unsigned builds show a SmartScreen "Unknown publisher" warning; document it. Code signing is a later, paid option.
- **Android:**
  - `flutter build apk --release --split-per-abi --flavor full`, plus the `play` flavor.
  - The keystore is never committed; a signing guide lives in `SETUP_ANDROID.md`.
- **Hosting:** GitHub Releases (free).
- **Updates:** the in-app "check for update" reads GitHub Releases.

---

## 17. Compliance & Policy Notes (must respect)

- **Google Play Accessibility policy:** autonomous initiate/plan/execute via the Accessibility API is prohibited. That's why the `play` flavor exists.
- **Android developer verification:** mandatory for sideloaded apps; global rollout planned for 2027.
- **WhatsApp:** official click-to-chat only, no unofficial clients or bulk messaging.
- **LinkedIn:** no automated posting bots. Draft + user presses Post.
- **India IT Rules (2026 amendment)** on synthetically generated information: label AI-generated or cloned voice audio clearly.
- **India DPDP Act:** privacy policy, consent, data minimisation, user rights (access/erase). Local-first design helps.
- **Voice cloning:** written consent from the voice owner, revocable, never used to impersonate the owner to others.
- **Free-tier APIs:** respect rate limits and terms. Disclose to users that some free tiers may use request data.
- **Licenses:** keep a `THIRD_PARTY_LICENSES.md`. Mark non-commercial components as optional and off in commercial builds.

---

## 18. References — what already exists (study behaviour, don't copy blindly)

**Personal / desktop agents**
- OpenClaw — open-source personal AI agent with a large skills marketplace, working through messaging apps. Reference for skills ecosystem and always-on assistant UX.
- Hermes Agent (Nous Research, 2026) — creates its own skills: after complex tasks it reflects and writes a new skill file. Reference for §8.10 reflection. Article: https://www.eweek.com/news/hermes-agent-self-improving-ai-tools/
- Moltis — runtime skill self-extension tools (`create_skill`, `update_skill`) that write only inside the skills folder: https://docs.moltis.org/skill-tools.html
- Microsoft UFO — Windows UI-automation agent (UI Automation + vision): https://github.com/microsoft/UFO
- Open Interpreter — LLM that runs code on your computer: https://github.com/OpenInterpreter/open-interpreter
- browser-use — LLM browser automation: https://github.com/browser-use/browser-use
- Leon — open-source personal assistant: https://github.com/leon-ai/leon
- Commercial references for "how it should feel": Google Gemini on Android (opens apps via intents), OpenAI ChatGPT agent, Anthropic Claude computer use.

**Phone agents (learning from demonstration)**
- AppAgent — multimodal agent that learns smartphone apps by exploration and demonstration: https://arxiv.org/abs/2312.13771
- Mobile-Agent (Alibaba X-PLUG): https://github.com/X-PLUG/MobileAgent
- Tasker / AutoInput — classic Android accessibility automation (UX reference).

**Self-improving agents & skills (research)**
- Agent Skills open standard (SKILL.md): https://agentskills.io
- Darwin Gödel Machine — agent that rewrites its own code, with sandboxing and traceability: https://sakana.ai/dgm/ , https://arxiv.org/abs/2505.22954
- Voyager — lifelong skill library written as code: https://arxiv.org/abs/2305.16291
- AutoSkill — experience-driven skill self-evolution: https://arxiv.org/abs/2603.01145
- EvoSkill — automated skill discovery from failures: https://arxiv.org/abs/2603.02766
- Memento-Skills (2026) — agents that create and refine their own skills.

**Tutoring**
- Khanmigo (Khan Academy) — Socratic AI tutor; ChatGPT Study Mode; Gemini Guided Learning — UX references for §8.6.

**Voice, vision, security building blocks**
- faster-whisper: https://github.com/SYSTRAN/faster-whisper · whisper.cpp: https://github.com/ggml-org/whisper.cpp
- edge-tts: https://github.com/rany2/edge-tts · Piper TTS (offline)
- Indic Parler-TTS (Hindi + emotions, Apache-2.0): https://huggingface.co/ai4bharat/indic-parler-tts
- IndicF5 (voice cloning, MIT): https://huggingface.co/ai4bharat/IndicF5
- openWakeWord: https://github.com/dscripka/openWakeWord
- Pipecat (low-latency voice agent pipeline reference): https://github.com/pipecat-ai/pipecat
- SpeechBrain speaker verification: https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
- OpenCV Zoo (YuNet, SFace): https://github.com/opencv/opencv_zoo
- ddgs search: https://pypi.org/project/ddgs/ · SearXNG: https://github.com/searxng/searxng · trafilatura: https://github.com/adbar/trafilatura
- Playwright (Python): https://playwright.dev/python/ · pywinauto: https://github.com/pywinauto/pywinauto
- sqlite-vec: https://github.com/asg017/sqlite-vec · Ollama: https://ollama.com · Groq tool use: https://console.groq.com/docs/tool-use
- Inno Setup: https://jrsoftware.org/isinfo.php · PyInstaller: https://pyinstaller.org · Flutter: https://flutter.dev

**Policies**
- Google Play AccessibilityService policy: https://support.google.com/googleplay/android-developer/answer/10964491
- Android developer verification: https://android-developers.googleblog.com/2026/03/android-developer-verification-rolling-out-to-all-developers.html

---

## 19. FINAL CHECKLIST

**Decisions (locked)**
- [x] Name: **Rishu**; persona: warm Hinglish friend-assistant, honest AI
- [x] Platforms: Windows desktop app (.exe installer) + Android single APK (≤ 30 MB)
- [x] UI: Flutter (one codebase); desktop brain: Python core; phone brain: Dart core
- [x] LLM: BYOK free tiers (Groq/Gemini/OpenRouter) + Ollama local; model IDs from config
- [x] Budget: ₹0 development; no unofficial APIs; permission-first
- [x] Business later: free → ads (non-conversation screens only) → premium; flags built, OFF

**Features**
- [ ] Security: PIN + face (liveness) + fingerprint + voice passphrase; step-up 2FA for R3; auto-lock; panic phrase; guest mode; profiles; encrypted data; activity log
- [ ] Permission engine R0–R3 + autonomy modes + prompt-injection defence + STOP
- [ ] Voice: hotkey/mic/assistant gesture; wake word (later); Hindi/Hinglish/English; streaming; barge-in
- [ ] Persona, emotion-aware tone, wellbeing rules
- [ ] Desktop control: apps, windows, files, system, screenshot, clipboard, dictation
- [ ] Browser & web: Playwright, search with sources, read/summarise, forms (R2)
- [ ] Communication: WhatsApp (wa.me), contacts, calls (phone), email draft, LinkedIn draft→user posts
- [ ] Tutor mode: syllabus, Socratic loop, cross-questions, quiz, flashcards, progress, own PDFs
- [ ] Research mode with citations and saved reports
- [ ] Productivity: reminders, alarms, timers, to-do, calendar, briefing, routines, focus timer, meeting notes
- [ ] Memory: profile, people, episodic, corrections; view/edit/forget/export
- [ ] Skills engine (SKILL.md), GitHub import with scanner, reflection proposals
- [ ] Teach mode: record → compile → test → replay (desktop, browser, Android full)
- [ ] Self-Update Lab: L1/L2/L3, sandbox, tests, review, 2FA, versions, auto-rollback, protected paths
- [ ] Vision: screen explain, OCR
- [ ] Custom voice (IndicF5) with consent flow + AI-voice label (optional)
- [ ] Multi-device: QR pairing, sync, phone→laptop control, offline mode
- [ ] Utilities: weather, news, music, translation, calculator, conversions
- [ ] Android: intents, default assistant, biometrics, flavors full/play, size ≤ 30 MB
- [ ] Interactive frontend: all screens in §12.2, rich cards, orb states, dark/light, Hindi/English

**Delivery**
- [ ] All phase acceptance criteria (§14) green
- [ ] `RishuSetup-x.y.z.exe` + `app-arm64-v8a-full-release.apk` on GitHub Releases
- [ ] SETUP_WINDOWS.md, SETUP_ANDROID.md, USER_GUIDE.md (Hindi + English)
- [ ] THIRD_PARTY_LICENSES.md, privacy policy draft
- [ ] GITM pack: synopsis, SRS, architecture & UML diagrams, test report, demo script, viva Q&A

---

## 20. Out of Scope for v1 (later)

- iOS app (needs a paid Apple developer account).
- Executing payments (Rishu only prepares and hands over).
- Play Store `full` flavor.
- Fine-tuning/training LLMs. Optional research phase: opt-in LoRA/DPO from the user's own feedback logs.
- On-device LLM on the phone: optional download later (e.g. a small Gemma-class model via Google AI Edge / llama.cpp), never bundled in the APK.
