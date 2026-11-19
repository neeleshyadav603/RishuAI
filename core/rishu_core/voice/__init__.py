"""Voice: microphone, speech-to-text, text-to-speech and playback."""

from .engine import VoiceEngine
from .mic import MicError, Recorder, Recording, to_wav
from .speaker import Speaker
from .stt import GroqTranscriber, SttError
from .text import clean_for_speech, is_devanagari, is_goodbye, split_for_speech
from .tts import Audio, ChainSynthesizer, TtsError

__all__ = [
    "Audio",
    "ChainSynthesizer",
    "GroqTranscriber",
    "MicError",
    "Recorder",
    "Recording",
    "Speaker",
    "SttError",
    "TtsError",
    "VoiceEngine",
    "clean_for_speech",
    "is_devanagari",
    "is_goodbye",
    "split_for_speech",
    "to_wav",
]
