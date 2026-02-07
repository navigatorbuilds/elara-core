"""
Elara Voice - Text to Speech
Uses Piper for local, fast, neural TTS.
"""

import logging
import subprocess
import tempfile
import wave
import os
from pathlib import Path
from typing import Optional

# Paths
VOICE_DIR = Path(__file__).parent
MODELS_DIR = VOICE_DIR / "models"
DEFAULT_MODEL = MODELS_DIR / "en_US-amy-medium.onnx"

# Check if piper is available
try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    logging.getLogger("elara.voice.tts").warning("Piper not available. Run: pip install piper-tts")

logger = logging.getLogger("elara.voice.tts")

# Global voice instance (lazy loaded)
_voice: Optional['PiperVoice'] = None


def _get_voice() -> 'PiperVoice':
    """Get or create the voice instance."""
    global _voice
    if _voice is None and PIPER_AVAILABLE:
        if DEFAULT_MODEL.exists():
            _voice = PiperVoice.load(str(DEFAULT_MODEL))
        else:
            raise FileNotFoundError(f"Voice model not found: {DEFAULT_MODEL}")
    return _voice


def synthesize_to_file(text: str, output_path: str) -> bool:
    """
    Synthesize text to a WAV file.
    Returns True on success.
    """
    if not PIPER_AVAILABLE:
        return False

    try:
        voice = _get_voice()

        # Use synthesize_wav which handles format automatically
        with wave.open(output_path, 'wb') as wav_file:
            voice.synthesize_wav(text, wav_file)

        return True
    except Exception as e:
        logger.error("TTS synthesis failed: %s", e)
        return False


def play_audio_windows(wav_path: str) -> bool:
    """Play audio file through Windows (from WSL)."""
    try:
        # Convert WSL path to Windows path
        win_path = subprocess.run(
            ['wslpath', '-w', wav_path],
            capture_output=True,
            text=True
        ).stdout.strip()

        # Use .NET SoundPlayer - simple and reliable
        ps_path = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
        ps_script = f"(New-Object Media.SoundPlayer '{win_path}').PlaySync()"

        result = subprocess.run(
            [ps_path, '-Command', ps_script],
            capture_output=True,
            timeout=30
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        logger.error("Audio playback failed: %s", e)
        return False


def speak(text: str, wait: bool = True) -> bool:
    """
    Speak the given text.

    Args:
        text: Text to speak
        wait: If True, wait for speech to complete

    Returns:
        True on success
    """
    if not PIPER_AVAILABLE:
        logger.warning("Piper TTS not available")
        return False

    try:
        # Create temp file for audio
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_path = f.name

        # Synthesize
        if not synthesize_to_file(text, temp_path):
            return False

        # Play
        success = play_audio_windows(temp_path)

        # Cleanup
        try:
            os.unlink(temp_path)
        except OSError:
            pass

        return success
    except Exception as e:
        logger.error("Speak failed: %s", e)
        return False


def speak_async(text: str) -> bool:
    """Speak without blocking (fire and forget)."""
    import threading
    thread = threading.Thread(target=speak, args=(text,))
    thread.daemon = True
    thread.start()
    return True


# Convenience functions
def say(text: str) -> bool:
    """Alias for speak."""
    return speak(text)


def whisper(text: str) -> bool:
    """Speak quietly (future: could adjust voice parameters)."""
    return speak(text)


# Test
if __name__ == "__main__":
    print(f"Piper available: {PIPER_AVAILABLE}")
    print(f"Model exists: {DEFAULT_MODEL.exists()}")

    if PIPER_AVAILABLE and DEFAULT_MODEL.exists():
        print("Testing speech synthesis...")
        speak("Hello. I can speak now. This is my voice.")
    else:
        print("Cannot test - missing dependencies or model")
