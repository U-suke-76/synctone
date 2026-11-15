# Changelog

[English](CHANGELOG.md) | [日本語](CHANGELOG.ja.md) | [한국어](CHANGELOG.ko.md)

---

All notable changes to **SyncTone** will be documented in this file.  
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- **Automated OBS Recording AV Sync Analysis (`📐 Recording Analysis (Timecode)` / `📂 Analyze recording...`)**: Added a timecode sweeping-bar mode driven by the audio clock phase and PyAV-based recording analysis (`mp4` / `mkv` / `mov` / `flv` / `ts`) that measures video-vs-audio offset with sub-frame (~1–2 ms) precision. Displays a 3-tier verdict (`<= 8 ms` OK / `<= 17 ms` minor / `> 17 ms` large) and offers one-click correction of the OBS video source's Render Delay filter without disturbing the microphone-calibrated audio sync offset.
- **Dedicated Direct3D 11 Window for OBS Game Capture (`🎮 Open Game Capture Window`)**: Added a top-level Direct3D 11 target window that automatically selects the primary high-VRAM GPU adapter so OBS "Game Capture" sources can hook and calibrate render delay directly in default shared-texture mode alongside "Window Capture".
- **Live Microphone Input Level Meter (`🎤 Input Level`)**: Added an always-on, real-time input level meter (dB scale, green / yellow for low input / red with a clipping warning) to the Audio Devices panel so you can check the mic level before measuring. It restarts automatically when the recording device changes and fails silently (`N/A`) if the microphone cannot be opened.
- **Live Level Display During Measurement**: The meter keeps moving while a measurement is running, fed directly by the measurement stream itself (`AudioEngine.play_and_record(level_callback=...)`), so no second stream competes for the microphone.

### Changed
- **Streamlined AV Sync Checker Modes & Video Delay Fine-Tuning**: Removed the redundant "🎵 Auditory Click (Metronome)" mode in favor of the two core workflows ("📺 Visual & Beep" and "📐 Recording Analysis"). When a video source is selected, the bottom trim buttons (`-5 ms / -1 ms / +1 ms / +5 ms`) now adjust the video source's Render Delay directly while keeping the audio sync offset intact.
- **GUI Module Architecture Refactoring**: Extracted background worker threads (`gui/workers.py`) and stylesheet definitions (`gui/styles.py`) out of `main_window.py` and modularized UI builder and OBS application helpers.

### Fixed
- **Fixed OBS Offset Difference Display Before Applying Measurement**: Fixed an issue where fetching or selecting an OBS audio source after measurement (while the manual offset spinbox was still at `0.0 ms`) displayed a difference against `0.0 ms` instead of the newly measured delay.
- **Fixed Dark-Theme Styling & Text Clipping in AV Sync Checker**: Scoped QSS selectors in `SyncVerifierWindow` to fix black background boxes behind labels, invisible radio button indicators, and clipped mode descriptions.

## [1.1.0] - 2026-10-24

### Added
- **Audio Device Refresh Button (`🔄 Refresh`)**: Added a one-click refresh button in the Audio Devices panel to reload connected earphones, audio interfaces, and microphones without restarting the application.
- **Automatic Native Sample Rate Fallback**: Added automatic hardware sample rate detection and fallback (e.g., to 44100 Hz) when 48000 Hz is not supported by the selected playback or recording device across measurement, test tone, and AV Sync Checker streams.
- **Microphone Input Level Diagnostics (Clipping & Low-Volume Warnings)**: Automatically inspects recorded peak amplitude after measurement and displays actionable warnings in the stability badge if signal clipping (`>= 0.98`) or insufficient input volume (`< 0.015`) is detected.
- **Linked Video Render Delay Trimming in AV Sync Checker**: When `🎥 Link Render Delay to Video Source` is enabled in the main window, clicking the `±1 ms` / `±5 ms` trim buttons inside the AV Sync Checker window now updates both the OBS audio sync offset and the video source's `Render Delay` filter simultaneously in real time.

### Changed
- **Expanded Plot Canvas & Improved Layout Proportions**: Increased the default window dimensions (`1140x950`) and reallocated vertical stretch to the waveform and cross-correlation visualizer while fixing clipped X-axis labels and peak badges.

### Fixed
- **Fixed Truncated Recording Window on High-Latency Devices (`AudioEngine.play_and_record`)**: Fixed a bug where `record_extra_seconds` was calculated but not zero-padded onto the playback buffer passed to `sd.playrec`, ensuring long-latency chirp returns (> 400 ms) are captured completely without cutoff.
- **Fixed Unwanted Auto-Overwrite of Manual Offset on Re-Measurement**: Fixed an issue where re-running a measurement after applying or fine-tuning the offset would automatically overwrite the user's manual offset spinbox value. New measurements now preserve the current manual offset until `⚡ Apply Measured` is explicitly clicked.


---

## [1.0.0] - Initial Release

### Added
- **Sub-Millisecond Chirp Latency Detection**: Logarithmic sweep generator (500 Hz – 4000 Hz) with Tukey windowing, FFT cross-correlation, and parabolic peak interpolation for sub-0.1 ms accuracy.
- **Inverted Polarity (180° Out-of-Phase) Microphone Detection**: Automatically detects inverted microphone phase using absolute correlation peaks and provides a 180° waveform polarity inversion toggle.
- **Multi-Run Measurement & Median Filtering**: Supports 1-run (Quick), 3-run (Standard), and 5-run (Thorough) modes with median filtering to reject transient ambient noise and evaluate reproducibility (jitter).
- **High-Performance Waveform & Cross-Correlation Visualizer (`pyqtgraph`)**: Features Level-of-Detail (LOD) Min/Max envelope rendering to prevent moiré artifacts in full view, full 48 kHz resolution in zoom view, and Hilbert analytic envelope plotting for clear correlation peaks.
- **Full OBS Studio 28+ (WebSocket v5) Integration**: One-click reading and writing of audio source sync offsets alongside linked video source `Render Delay` (`gpu_delay`) filters for karaoke lyrics, rhythm games, and webcams.
- **Real-Time AV Sync Checker Window**: Independent verification dialog featuring 60 FPS "Visual Flash & Beep" mode (for OBS Window Capture) and "Auditory Click" metronome mode with direct `±1 ms` / `±5 ms` OBS live-trimming buttons.
- **Multilingual UI Support (5 Languages)**: Dynamic real-time localization in Japanese (`ja`), English (`en`), Korean (`ko`), Traditional Chinese (`zh_TW`), and Simplified Chinese (`zh_CN`).
