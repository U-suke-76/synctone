# SyncTone

[English](README.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

---

**"Transparent, visible, and millisecond-accurate."**  
An open-source OBS audio synchronization assistant designed for singing and music streamers.

---

## Features

* **Sub-Millisecond Accuracy Detection**  
  Measures latency with sub-0.1 ms precision using logarithmic chirp signals (500 Hz – 4000 Hz) optimized for human hearing and noise rejection, combined with FFT cross-correlation and parabolic peak interpolation.
* **Lightweight & Low Resource Consumption (Electron-Free)**  
  Built natively with Python + PySide6 (Qt 6) + pyqtgraph for near-instant startup and minimal memory footprint.
* **Visual Feedback for Peace of Mind**  
  No black-box mystery. Visually inspect reference and microphone signal alignment along with the cross-correlation peak directly on clear interactive graphs.
* **Full OBS Studio 28+ (WebSocket v5) Integration**  
  Instantly applies detected delay (ms) to target OBS audio sources (Desktop Audio or Microphone) with a single click.
* **Linked Video Render Delay for Karaoke, Rhythm Games & Webcams**  
  Synchronizes video sources (Game Capture, Capture Cards, Webcams) via OBS "Render Delay" filters alongside audio, eliminating early karaoke lyrics (flying text) and camera desync.
* **AV Sync Checker (Visual & Recording-Based Verification)**  
  Verify and calibrate video-audio sync on the spot. Features two modes: "📺 Visual & Beep (AV Sync)" for real-time visual inspection, and "📐 Recording Analysis (Timecode)" which decodes a ~5-second OBS recording to measure video-vs-audio offset with ~1–2 ms precision and updates the video source's Render Delay automatically. Includes a dedicated Direct3D 11 target window so both OBS "Window Capture" and "Game Capture" sources can be calibrated directly.
* **100% Local & Privacy-Conscious**  
  Zero telemetry or internet traffic. Audio recordings are analyzed strictly in memory and immediately discarded.

---

## System Architecture

* **GUI**: PySide6 (Qt 6)
* **Waveform Visualization**: pyqtgraph (low-overhead, high-framerate plotting)
* **Audio I/O**: sounddevice (PortAudio / Windows WASAPI)
* **DSP / Analysis**: NumPy / SciPy (cross-correlation analysis & chirp generation)
* **Recording Decode / AV Sync Analysis**: PyAV (FFmpeg-based video & audio decoding)
* **OBS Integration**: obsws-python (WebSocket v5 protocol)

---

## Quick Start

### 1. Environment Setup & Installation

```bash
# Create virtual environment
python -m venv .venv

# Activate (PowerShell)
.venv\Scripts\Activate.ps1

# Install package and dependencies
pip install -e .
```

### 2. Launching the App

```bash
python run.py
```
or
```bash
synctone
```

---

## How to Use

1. **Verify OBS Studio Settings**  
   * In OBS Studio, open `[Tools]` → `[WebSocket Server Settings]` and ensure the WebSocket server is enabled (default port: 4455).
2. **Launch & Connect SyncTone**  
   * Open SyncTone, enter your port and server password (if configured), and click **"Connect to OBS"**.
3. **Select Audio Devices**  
   * Select your playback device (earphones/speakers used for backing tracks) and recording device (the microphone you want to calibrate).
4. **Run Latency Measurement**  
   * **Take off your earphone and place it directly against your microphone**.
   * Click **"Start Measurement"** (a quiet ~1.5-second sweep tone will play).
5. **Inspect Waveforms & Fine-Tune**  
   * Check the detected delay (ms), waveform alignment, and correlation peak.
   * Adjust manually using the slider or spin box if needed.
6. **Apply to OBS**  
   * Choose your target audio source (e.g., `Desktop Audio (Recommended: delay backing track)`).
   * **If syncing karaoke lyrics screens or live camera feeds:**
     * Check `🎥 Link Render Delay to Video Source` and select your video source (Game Capture, Capture Card, etc.).
   * Click **"Apply Results to OBS"** (audio sync offset and video render delay will be applied immediately).
7. **Verify & Auto-Calibrate Video Delay with AV Sync Checker**  
   * Click **"🎧 AV Sync Check"** to open the verification window (if using OBS Game Capture, click **"🎮 Open Game Capture Window"** to open the dedicated Direct3D 11 target window).
   * **📺 Visual & Beep Mode**: Capture the window in OBS and visually verify that the center flash and beep sound align when the sweep bar crosses `0 ms`.
   * **📐 Recording Analysis (Timecode) Mode**: Record ~5 seconds in OBS while playing, then click **"📂 Analyze recording..."** and select the recorded file. SyncTone automatically calculates the exact video-vs-audio offset (ms) and lets you apply the correction directly to the OBS video source's Render Delay filter while preserving your calibrated audio sync offset.
   * Fine-tune latency on the fly using the `±1 ms` and `±5 ms` buttons at the bottom of the verification window.

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Building Standalone Executable (.exe)

You can build a portable, single-file executable (`dist/SyncTone.exe`) that runs on Windows without requiring a Python environment:

```bash
pip install -e .[dev]
python build.py
```

---

## License

MIT License
