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
        "not_heard": "Mujhe kuch sunai nahi diya. Mic ke paas bol kar dobara try karo.",
        "mic_silent": "Mic se bilkul bhi awaaz nahi aa rahi. Windows Settings > Privacy & security > Microphone mein "
        "'Microphone access' aur 'Let desktop apps access your microphone' ON karo, aur mic ka mute button check karo.",
        "voice_input_off": "Voice input abhi available nahi hai",
        "voice_output_failed": "Awaaz mein jawab nahi suna paaya",
        "locked": "Rishu locked hai. Pehle PIN, Windows Hello ya bolkar password se unlock karo.",
        "lock_needs_pin": "Lock karne ke liye pehle Settings mein PIN set karo.",
        "unlock_failed": "Password match nahi hua. Dobara try karo.",
        "unlock_paused": "Bahut baar galat koshish hui. 30 second baad try karo.",
        "unlock_no_hello": "Is PC par Windows Hello set nahi hai. PIN se unlock karo.",
        "reminder_while_locked": "Ek reminder ka time ho gaya hai. Unlock karke dekho.",
        "phrase_saved": "Bolkar password save ho gaya. Lock screen par mic dabakar wahi bolna.",
        "phrase_too_short": "Password thoda lamba bolo, kam se kam teen-chaar shabd.",
    },
    "en": {
        "stopped": "Okay, stopped.",
        "max_steps": "This task needed more steps than I take in one go, so I stopped here. Tell me to continue if you want.",
        "no_llm": "I can't reach any AI model right now, so I can only do basic commands (open apps, time, notes).",
        "no_llm_setup": "Setup: add a free API key (for example Groq) in Settings, or run Ollama on this laptop.",
        "offline_prefix": "(Offline mode) ",
        "denied": "Okay, I did not do that.",
        "step_up_unavailable": "This action needs an extra security check that is not set up yet, so I did not do it.",
        "not_heard": "I didn't hear anything. Please speak closer to the mic and try again.",
        "mic_silent": "The microphone sends only silence. In Windows Settings > Privacy & security > Microphone, turn on "
        "'Microphone access' and 'Let desktop apps access your microphone', and check the mic's mute button.",
        "voice_input_off": "Voice input is not available right now",
        "voice_output_failed": "I couldn't speak the reply aloud",
        "locked": "Rishu is locked. Unlock with your PIN, Windows Hello or your spoken password first.",
        "lock_needs_pin": "Set a PIN in Settings first, then Rishu can lock.",
        "unlock_failed": "That did not match. Please try again.",
        "unlock_paused": "Too many wrong tries. Try again in 30 seconds.",
        "unlock_no_hello": "Windows Hello is not set up on this PC. Use your PIN.",
        "reminder_while_locked": "A reminder is due. Unlock Rishu to see it.",
        "phrase_saved": "Spoken password saved. On the lock screen, press the mic and say it.",
        "phrase_too_short": "Please say a longer phrase, at least three or four words.",
    },
}
_STRINGS["hi"] = _STRINGS["hinglish"]


def t(key: str, language: str = "hinglish") -> str:
    table = _STRINGS.get(language) or _STRINGS["hinglish"]
    return table.get(key) or _STRINGS["en"][key]
