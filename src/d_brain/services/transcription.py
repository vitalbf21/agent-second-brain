"""Local transcription service using faster-whisper."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy-load the model to avoid import at module level
_model = None


def _get_model():
    """Get or initialize the whisper model (lazy load)."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading whisper model (base, CPU)...")
        # Use "base" model for balance between speed and accuracy
        # On CPU, this takes ~30s first time, ~2s after
        _model = WhisperModel("base", device="cpu", compute_type="int8")
        logger.info("Whisper model loaded")
    return _model


class DeepgramTranscriber:
    """Service for transcribing audio using local faster-whisper.

    Note: Class name kept for backward compatibility with chat.py import.
    """

    def __init__(self, api_key: str = "") -> None:
        # api_key ignored - we use local whisper
        pass

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Audio file content (ogg, mp3, wav, etc.)

        Returns:
            Transcribed text
        """
        import tempfile
        import os

        logger.info("Starting transcription, audio size: %d bytes", len(audio_bytes))

        # faster-whisper needs a file, write to temp
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            model = _get_model()
            segments, info = model.transcribe(
                tmp_path,
                language="ru",
                beam_size=5,
                vad_filter=True,
            )

            # Collect all segments
            transcript_parts = []
            for segment in segments:
                transcript_parts.append(segment.text.strip())

            transcript = " ".join(transcript_parts)
            logger.info("Transcription complete: %d chars (detected lang: %s)", len(transcript), info.language)
            return transcript
        except Exception as e:
            logger.exception("Transcription failed")
            raise
        finally:
            os.unlink(tmp_path)

