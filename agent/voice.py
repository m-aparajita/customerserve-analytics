"""
Voice input — speech-to-text via Groq Whisper.

STT only. Transcribed text is not a separate trust boundary: it feeds into
the same respond() pipeline as typed input, so guardrails/RBAC apply unchanged.
"""

import os

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

_MODEL_NAME = "whisper-large-v3-turbo"

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def transcribe_audio(audio_path: str) -> str:
    """Transcribe a recorded audio file to text. Returns "" on empty input or failure."""
    if not audio_path:
        return ""
    try:
        with open(audio_path, "rb") as f:
            result = _get_client().audio.transcriptions.create(
                file=f,
                model=_MODEL_NAME,
            )
        return (result.text or "").strip()
    except Exception as e:
        print(f"[Voice] Transcription failed: {e}")
        return ""
