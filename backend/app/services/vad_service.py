import collections
import logging

import webrtcvad

from app.config import get_settings

logger = logging.getLogger(__name__)


class VADService:
    """
    Voice Activity Detection using webrtcvad.
    Aggregates small PCM frames into complete speech chunks based on silence.
    Expects: 16-bit Mono PCM at 16 kHz.
    """

    def __init__(self):
        settings = get_settings()
        aggressiveness = settings.vad_aggressiveness
        frame_duration_ms = settings.vad_frame_duration_ms
        padding_duration_ms = settings.vad_padding_duration_ms

        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = 16000
        self.frame_size = int(self.sample_rate * frame_duration_ms / 1000) * 2  # 16-bit

        self.num_padding_frames = int(padding_duration_ms / frame_duration_ms)
        self.ring_buffer: collections.deque = collections.deque(maxlen=self.num_padding_frames)
        self.triggered = False
        self.voiced_frames: list[bytes] = []

    def get_speech_chunks(self, audio_data: bytes):
        """Yield complete speech chunks extracted from raw audio data."""
        offset = 0
        while offset + self.frame_size <= len(audio_data):
            frame = audio_data[offset : offset + self.frame_size]
            offset += self.frame_size

            is_speech = self.vad.is_speech(frame, self.sample_rate)

            if not self.triggered:
                self.ring_buffer.append((frame, is_speech))
                num_voiced = sum(1 for _, s in self.ring_buffer if s)

                if num_voiced > 0.6 * self.ring_buffer.maxlen:
                    logger.debug("VAD: speech start")
                    self.triggered = True
                    for f, _ in self.ring_buffer:
                        self.voiced_frames.append(f)
                    self.ring_buffer.clear()
            else:
                self.voiced_frames.append(frame)
                self.ring_buffer.append((frame, is_speech))

                num_unvoiced = sum(1 for _, s in self.ring_buffer if not s)
                if num_unvoiced > 0.9 * self.ring_buffer.maxlen:
                    logger.debug("VAD: speech end")
                    self.triggered = False
                    yield b"".join(self.voiced_frames)
                    self.voiced_frames = []
                    self.ring_buffer.clear()

    def close(self) -> bytes | None:
        """Flush remaining voiced frames on stream end."""
        if self.triggered and self.voiced_frames:
            logger.debug("VAD: flushing remaining frames")
            chunk = b"".join(self.voiced_frames)
            self.voiced_frames = []
            self.triggered = False
            return chunk
        return None
