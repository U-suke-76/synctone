# Changelog

[English](CHANGELOG.md) | [日本語](CHANGELOG.ja.md) | [한국어](CHANGELOG.ko.md)

---

All notable changes to **SyncTone** will be documented in this file.  
This project adheres to [Semantic Versioning](https://semver.org/).

---

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
