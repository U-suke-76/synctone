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
* **Real-Time AV Sync Checker (Auditory & Visual Verification)**  
  Verify sync results on the spot. Features two verification modes: "Visual Flash & Beep" (for window capture to check visual-audio alignment) and "Metronome Click" (for ear-based auditory check). Provides real-time ±1 ms / ±5 ms fine-tuning buttons directly linked to OBS.
* **100% Local & Privacy-Conscious**  
  Zero telemetry or internet traffic. Audio recordings are analyzed strictly in memory and immediately discarded.

---

## System Architecture

* **GUI**: PySide6 (Qt 6)
* **Waveform Visualization**: pyqtgraph (low-overhead, high-framerate plotting)
* **Audio I/O**: sounddevice (PortAudio / Windows WASAPI)
* **DSP / Analysis**: NumPy / SciPy (cross-correlation analysis & chirp generation)
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
7. **Verify with AV Sync Checker**  
   * Click **"🎧 AV Sync Check"** to open the verification window.
   * **Visual & Beep Mode**: Add this window as a "Window Capture" source in OBS. Verify that the flash and beep sound match precisely when the sweep bar hits center (0 ms).
   * **Auditory Click Mode**: Listen to the metronome click via OBS Audio Monitoring to verify that both sound streams hit as a single unified beat without doubling or flamming.
   * Fine-tune latency on the fly using the `±1 ms` and `±5 ms` buttons inside the verification window.

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
