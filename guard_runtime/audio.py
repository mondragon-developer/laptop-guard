"""Small, generated alarm tones; no assets or extra audio dependencies."""
from array import array
import math
import sys
import wave

SAMPLE_RATE = 44100


def pcm_tone(style="siren"):
    """One second of stereo 16-bit PCM at the original alarm's amplitude."""
    samples = array("h")
    for i in range(SAMPLE_RATE):
        if style == "beep":
            frequency = 800 if (i // (SAMPLE_RATE // 4)) % 2 == 0 else 1200
            value = int(16000 * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE))
        else:
            value = 16000 if (i * 1600 // SAMPLE_RATE) % 2 == 0 else -16000
        samples.extend((value, value))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def write_alarm(path):
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(pcm_tone())
