# Rishu

Rishu is a voice-first personal AI assistant for Windows (Android later). It
understands Hindi, Hinglish and English, talks back in a natural voice, does
things on your computer with your permission, teaches, searches the web with
sources, remembers what you ask it to, and sets reminders.

## Download (Windows 10/11)

Get **`RishuSetup-x.y.z.exe`** from the latest
[Release](https://github.com/neeleshyadav603/RishuAI/releases/latest) and run it.
Nothing else needs to be installed (no Python). Windows may say "Unknown
publisher" because the installer is not code-signed yet: **More info → Run anyway**.

On first start Rishu asks for your name, language, voice, and a free Groq API
key (console.groq.com). Without a key, basic offline commands still work.

Demo script: [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) · Progress: [docs/PROGRESS.md](docs/PROGRESS.md)

## What Rishu can do now

| Area | Examples |
| --- | --- |
| Voice | Mic button, Ctrl+Space in the app, Ctrl+Shift+Space from any app; replies spoken in a natural Hindi or Indian-English voice; STOP / Esc anytime |
| Apps and web | "Chrome kholo", "gitm.edu.in kholo", "YouTube pe Kesariya chalao", "Google pe GITM admission search karo" |
| Answers with sources | "Aaj ki AI news search karo" (sources card, click to open) |
| Teaching | "Mujhe quantum computing padhao", then ask follow-up questions |
| Messages (you press Send) | "WhatsApp pe likho: main 10 minute late hoon", "HOD ko leave ka email draft karo" |
| Computer | "Awaaz badhao", "screenshot lo", "computer lock karo", "battery kitni hai" |
| Reminders | "1 minute baad paani peene ka reminder lagao" (shown and spoken) |
| Memory | "Yaad rakho: mera favourite subject DAA hai", "kya yaad hai mere baare mein?" |
| Weather | "Gurugram ka mausam batao" |
| Screen | "Screen par kya hai, samjhao", "yeh error kya hai?" |
| Safety | Permission cards before important actions, activity log, keys encrypted on this PC |

## What is in the repo

| Path | What |
| --- | --- |
| `RISHU_SPEC.md` | Full product and build spec |
| `docs/Rishu_SRS_v1.0.pdf` | Software Requirements Specification |
| `core/` | Python core: agent loop, LLM router, tools, permissions, voice, local API |
| `app/` | Flutter app (Windows now, Android later) |
| `shared/` | Prompts and the app↔core protocol schema |
| `config/` | Models, permission policy, defaults |
| `installer/` | Inno Setup script for the Windows installer |

## Develop

```bash
cd core
pip install -e ".[web,voice,dev]"
python -m rishu_core            # text chat in the terminal
python -m pytest -q             # tests
```

Builds of the Windows installer run on GitHub Actions (`.github/workflows/build.yml`).
