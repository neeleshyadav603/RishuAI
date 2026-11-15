"""User-facing strings produced by the core itself (not by the LLM).

Small on purpose: the full i18n tables live in the app. Keys here must exist
for every language.
"""

from __future__ import annotations

_STRINGS: dict[str, dict[str, str]] = {
    "hinglish": {
        "stopped": "Theek hai, ruk gaya.",
        "max_steps": "Yeh kaam mere ek baar ke step limit se lamba nikla, isliye main yahin ruk raha hoon. Aap bolo to aage badhata hoon.",
        "no_llm": "Abhi main kisi AI model se connect nahi ho pa raha, isliye sirf basic commands kar sakta hoon (app kholna, time, notes).",
        "no_llm_setup": "Setup: ek free API key (jaise Groq) Settings mein daalo, ya laptop par Ollama chalao.",
        "offline_prefix": "(Offline mode) ",
        "denied": "Theek hai, yeh nahi kiya.",
        "step_up_unavailable": "Is kaam ke liye extra security check chahiye, jo abhi set up nahi hai. Isliye yeh nahi kiya.",
    },
    "en": {
        "stopped": "Okay, stopped.",
        "max_steps": "This task needed more steps than I take in one go, so I stopped here. Tell me to continue if you want.",
        "no_llm": "I can't reach any AI model right now, so I can only do basic commands (open apps, time, notes).",
        "no_llm_setup": "Setup: add a free API key (for example Groq) in Settings, or run Ollama on this laptop.",
        "offline_prefix": "(Offline mode) ",
        "denied": "Okay, I did not do that.",
        "step_up_unavailable": "This action needs an extra security check that is not set up yet, so I did not do it.",
    },
}
_STRINGS["hi"] = _STRINGS["hinglish"]


def t(key: str, language: str = "hinglish") -> str:
    table = _STRINGS.get(language) or _STRINGS["hinglish"]
    return table.get(key) or _STRINGS["en"][key]
