import collections
import logging
import math
import struct

import webrtcvad

from app.config import get_settings

logger = logging.getLogger(__name__)


def calculate_frame_energy(frame: bytes) -> float:
    """Calculate the Root Mean Square (RMS) energy of a 16-bit mono PCM frame."""
    count = len(frame) // 2
    if count == 0:
        return 0.0
    shorts = struct.unpack(f"<{count}h", frame)
    sum_squares = sum(s * s for s in shorts)
    return math.sqrt(sum_squares / count)


class VADService:
    """
    Robust Voice Activity Detection using webrtcvad + RMS Energy Gating.
    Aggregates small PCM frames into complete speech utterances.

    Anti-noise features:
    - Rejects sub-threshold background noise via RMS energy gating
    - Requires sustained voiced frames before triggering speech state
    - Maintains pre-roll buffer to avoid clipping initial phonemes
    - Requires minimum speech duration before emitting utterance (rejects clicks/taps)
    - Enforces silence hangover period to allow natural pauses between words
    """

    def __init__(self):
        settings = get_settings()
        self.aggressiveness = getattr(settings, "vad_aggressiveness", 3)
        self.frame_duration_ms = getattr(settings, "vad_frame_duration_ms", 30)
        self.padding_duration_ms = getattr(settings, "vad_padding_duration_ms", 300)
        self.min_speech_ms = getattr(settings, "vad_min_speech_ms", 400)
        self.silence_hangover_ms = getattr(settings, "vad_silence_hangover_ms", 800)
        self.energy_threshold = float(getattr(settings, "vad_energy_threshold", 300.0))

        self.vad = webrtcvad.Vad(getattr(settings, "vad_aggressiveness", 2))
        self.sample_rate = 16000
        # Frame size in bytes (16-bit mono = 2 bytes/sample)
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000) * 2

        self.num_padding_frames = max(3, int(self.padding_duration_ms / self.frame_duration_ms))
        self.hangover_frames_needed = max(6, int(self.silence_hangover_ms / self.frame_duration_ms))
        self.min_speech_bytes = int((self.sample_rate * (self.min_speech_ms / 1000.0)) * 2)

        self.ring_buffer: collections.deque = collections.deque(maxlen=self.num_padding_frames)
        self.triggered = False
        self.voiced_frames: list[bytes] = []
        self.unvoiced_count = 0
        self.voiced_frame_count = 0

    def get_speech_chunks(self, audio_data: bytes):
        """
        Yield complete speech chunks extracted from raw audio data.
        Silences, isolated clicks, and noise are filtered out.
        """
        offset = 0
        while offset + self.frame_size <= len(audio_data):
            frame = audio_data[offset : offset + self.frame_size]
            offset += self.frame_size

            # 1. Energy check
            rms = calculate_frame_energy(frame)
            is_energy_above_floor = rms >= self.energy_threshold

            # 2. WebRTC VAD check (requires 10, 20, or 30ms frame)
            try:
                is_vad_speech = self.vad.is_speech(frame, self.sample_rate)
            except Exception:
                is_vad_speech = False

            # Frame is considered voiced only if BOTH webrtc and energy criteria are met
            is_speech = is_vad_speech and is_energy_above_floor

            if not self.triggered:
                self.ring_buffer.append((frame, is_speech))
                num_voiced = sum(1 for _, s in self.ring_buffer if s)

                # Require a sustained ratio of voiced frames in the ring buffer before triggering
                if num_voiced >= int(0.4 * self.ring_buffer.maxlen) and is_speech:
                    logger.debug("VAD: speech start detected (RMS=%.1f)", rms)
                    self.triggered = True
                    self.unvoiced_count = 0
                    self.voiced_frame_count = 0
                    # Prepend pre-roll buffer to preserve starting consonants
                    for f, _ in self.ring_buffer:
                        self.voiced_frames.append(f)
                        self.voiced_frame_count += 1
                    self.ring_buffer.clear()
            else:
                self.voiced_frames.append(frame)
                if is_speech:
                    self.voiced_frame_count += 1
                    self.unvoiced_count = 0
                else:
                    self.unvoiced_count += 1

                # Check if silence hangover duration is reached
                if self.unvoiced_count >= self.hangover_frames_needed:
                    logger.debug(
                        "VAD: speech end detected | total_frames=%d, voiced=%d, unvoiced=%d",
                        len(self.voiced_frames),
                        self.voiced_frame_count,
                        self.unvoiced_count,
                    )
                    chunk = b"".join(self.voiced_frames)
                    voiced_count = self.voiced_frame_count
                    self.triggered = False
                    self.voiced_frames = []
                    self.unvoiced_count = 0
                    self.voiced_frame_count = 0
                    self.ring_buffer.clear()

                    # Only yield if utterance has sufficient speech content (min 4000 bytes ~ 125ms)
                    if len(chunk) >= 4000 and voiced_count >= 3:
                        logger.info("VAD: valid speech utterance yielded (%d bytes)", len(chunk))
                        yield chunk
                    else:
                        logger.debug("VAD: discarded transient noise/click (%d bytes)", len(chunk))

    def flush(self) -> bytes | None:
        """Flush remaining voiced frames on client speech_end signal."""
        if not self.triggered and not self.voiced_frames:
            self.ring_buffer.clear()
            self.unvoiced_count = 0
            self.voiced_frame_count = 0
            return None

        frames_to_flush = list(self.voiced_frames)
        if self.ring_buffer:
            for f, _ in self.ring_buffer:
                frames_to_flush.append(f)

        voiced_count = self.voiced_frame_count
        self.triggered = False
        self.voiced_frames = []
        self.unvoiced_count = 0
        self.voiced_frame_count = 0
        self.ring_buffer.clear()

        if frames_to_flush and voiced_count >= 3:
            chunk = b"".join(frames_to_flush)
            if len(chunk) >= 2000:  # ~62.5ms minimum for short emergency utterances
                logger.info("VAD: valid speech utterance flushed (%d bytes)", len(chunk))
                return chunk
        return None

    def close(self) -> bytes | None:
        """Flush remaining voiced frames on stream end."""
        return self.flush()
