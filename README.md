# Rishu

Rishu is a voice-first personal AI assistant for Windows and Android. It
understands Hindi, Hinglish and English, acts on your behalf with your
permission, teaches, researches, remembers, and learns new skills.

**Status:** under active development. See [docs/PROGRESS.md](docs/PROGRESS.md).

## What is here

| Path | What |
| --- | --- |
| `RISHU_SPEC.md` | Full product and build spec |
| `docs/Rishu_SRS_v1.0.pdf` | Software Requirements Specification |
| `core/` | Python desktop core: agent loop, LLM router, tools, permissions |
| `app/` | Flutter app for Windows and Android (from Phase 2) |
| `shared/` | Prompts, protocol schema, bundled skills |
| `config/` | Models, permission policy, defaults |

## Try the core (text chat)

```bash
cd core
pip install -e ".[web,dev]"
export GROQ_API_KEY=...        # a free key from console.groq.com (PowerShell: $env:GROQ_API_KEY="...")
python -m rishu_core           # or: python -m rishu_core --once "Chrome kholo"
```

Without an API key, Rishu still handles basic offline commands such as
"notepad kholo", "time kya hua hai" and "note likho: ...".

## Downloads

The Windows installer and the Android APK will appear under **Releases** once
the app phases are built.
