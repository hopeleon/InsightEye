from __future__ import annotations


class RealtimeTranscriber:
    """Adapter placeholder for streaming ASR integration."""

    def append_audio(self, chunk: bytes) -> None:
        del chunk
        raise NotImplementedError("Realtime audio transcription adapter is not implemented yet.")

    def close(self) -> None:
        return
