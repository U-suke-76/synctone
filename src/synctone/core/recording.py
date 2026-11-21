"""Decode an OBS recording (video + audio) into the plain arrays used by the AV sync analysis.

The recording is expected to show the AV Sync Checker in its recording-analysis mode (sweeping bar timecode
plus periodic beeps). Decoding uses PyAV (FFmpeg libraries), which keeps the container timestamps of both
streams on the same time base.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np

from synctone.core.av_analysis import (
    AvOffsetResult, detect_beep_onsets, bar_positions_from_profiles, estimate_av_offset,
)


@dataclass
class DecodedRecording:
    """Audio samples and per-frame column brightness profiles with container timestamps."""
    audio: np.ndarray  # mono float32 samples
    audio_sample_rate: int
    audio_start_s: float  # container time of the first audio sample
    frame_times: np.ndarray  # presentation time of each video frame (seconds)
    profiles: np.ndarray  # (n_frames, width) mean brightness of each pixel column


def decode_recording(path: str, max_seconds: Optional[float] = None) -> DecodedRecording:
    """Decode the first audio and video streams of a recording.

    Args:
        path: Path of the recording file (mp4 / mkv / mov ...).
        max_seconds: Optionally stop after this many seconds of video.

    Raises:
        ValueError: If the file has no audio or no video stream, or no frame could be decoded.
    """
    import av  # imported lazily: only needed for recording analysis

    with av.open(path) as container:
        if not container.streams.video:
            raise ValueError("The recording has no video stream.")
        if not container.streams.audio:
            raise ValueError("The recording has no audio stream.")
        vstream = container.streams.video[0]
        astream = container.streams.audio[0]
        vstream.thread_type = "AUTO"

        resampler = av.AudioResampler(format="flt", layout="mono")
        audio_chunks = []
        audio_start: Optional[float] = None
        audio_rate = int(astream.rate or astream.codec_context.sample_rate)
        frame_times = []
        profiles = []

        video_done = False
        for packet in container.demux(vstream, astream):
            if packet.stream is vstream:
                if video_done:
                    continue
                for frame in packet.decode():
                    if frame.time is None:
                        continue
                    if max_seconds is not None and frame.time > max_seconds:
                        video_done = True
                        break
                    gray = frame.to_ndarray(format="gray")
                    profiles.append(gray.mean(axis=0, dtype=np.float32))
                    frame_times.append(float(frame.time))
            else:
                for frame in packet.decode():
                    if audio_start is None and frame.time is not None:
                        audio_start = float(frame.time)
                    if max_seconds is not None and frame.time is not None and frame.time > max_seconds + 1.0:
                        if video_done:
                            break
                        continue
                    audio_rate = int(frame.sample_rate)
                    for out in resampler.resample(frame):
                        audio_chunks.append(out.to_ndarray().reshape(-1))
            if video_done and max_seconds is not None:
                # Stop demuxing once both video and sufficient audio up to max_seconds are collected
                if audio_start is not None and len(audio_chunks) > 0:
                    decoded_audio_s = audio_start + sum(len(c) for c in audio_chunks) / max(1, audio_rate)
                    if decoded_audio_s > max_seconds:
                        break

        for out in resampler.resample(None):
            audio_chunks.append(out.to_ndarray().reshape(-1))

    if not frame_times:
        raise ValueError("No video frame could be decoded.")
    if not audio_chunks:
        raise ValueError("No audio could be decoded.")

    order = np.argsort(frame_times)
    return DecodedRecording(
        audio=np.concatenate(audio_chunks).astype(np.float32),
        audio_sample_rate=audio_rate,
        audio_start_s=audio_start or 0.0,
        frame_times=np.asarray(frame_times, dtype=np.float64)[order],
        profiles=np.stack(profiles).astype(np.float32)[order],
    )


def analyze_decoded_recording(rec: DecodedRecording) -> AvOffsetResult:
    """Run the AV sync analysis on a decoded recording.

    Raises:
        ValueError: If too few beeps or no moving bar could be found.
    """
    beeps = detect_beep_onsets(rec.audio, rec.audio_sample_rate) + rec.audio_start_s
    bar_x = bar_positions_from_profiles(rec.profiles)
    return estimate_av_offset(beeps, rec.frame_times, bar_x)


def analyze_recording(path: str, max_seconds: Optional[float] = None) -> AvOffsetResult:
    """Decode a recording file and estimate its audio/video offset (positive: video later than audio)."""
    return analyze_decoded_recording(decode_recording(path, max_seconds=max_seconds))
