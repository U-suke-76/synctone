"""Internationalization (i18n) module supporting Japanese, English, and Korean."""

from typing import Dict, Any, Optional
from PySide6.QtCore import QLocale

LANGUAGES = {
    "ja": "日本語",
    "en": "English",
    "ko": "한국어",
    "zh_TW": "繁體中文",
    "zh_CN": "简体中文",
}

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ja": {
        # Window & Header
        "app_title": "SyncTone - OBS音声同期アシスタント",
        "lang_select": "言語 / Language:",
        "status_ready": "準備完了: OBSを起動して接続し、測定を開始してください。",
        "status_measuring": "チャープ信号を再生中 (全{total}回)...",
        "status_sampling": "測定中: {current} / {total} 回目のサンプリング完了",
        "status_measured_auto": "測定完了: {delay:.1f} ms を自動反映しました。",
        "status_measured_guide": "測定完了: {delay:.1f} ms の遅延を検出。「⚡ 測定結果を反映」を押すと山がピタッと一致します。",
        "status_applied_adj": "測定値 {delay:.1f} ms を手動調整に反映しました。",
        "status_reset_zero": "手動オフセットを 0.0 ms (生遅延) にリセットしました。",
        "status_fetched_obs": "OBSから 「{name}」 の設定値 ({offset} ms) をプレビューに反映しました。波形のズレを確認できます。",
        "status_applied_obs": "反映成功: {name} = {offset} ms をOBSに返しました。",
        "status_obs_loaded": "OBSから {count} 個の音声ソースを読み込みました。",
        "status_error": "測定エラーが発生しました。",

        # OBS Section
        "obs_group": "1. OBS Studio 連携 (WebSocket v5)",
        "obs_host_port": "ホスト/ポート:",
        "obs_password": "パスワード:",
        "obs_password_placeholder": "設定している場合のみ入力",
        "obs_connect": "OBSに接続",
        "obs_disconnect": "切断",
        "obs_connected": "● 接続中",
        "obs_disconnected": "● 未接続",
        "obs_no_sources": "音声ソースが見つかりません",
        "obs_not_connected_source": "OBS未接続 (ソース選択不可)",
        "obs_recommended_source": "(推奨: オケ遅延)",

        # Audio Section
        "audio_group": "2. 測定用 デバイス ＆ 音量設定",
        "audio_playback": "再生 (イヤホン/オケ音源):",
        "audio_recording": "録音 (対象マイク入力):",
        "audio_volume": "測定音量:",
        "audio_test_tone": "音量試聴",
        "audio_test_tooltip": "イヤホンから短い確認音を鳴らして音量をチェックします",

        # Plot Section
        "plot_group": "3. 測定波形・一致度可視化",
        "plot_align": "補正プレビュー (重ね合わせ)",
        "plot_align_tooltip": "検出された遅延分シフトして波形を重ね合わせます",
        "plot_invert": "極性反転補正 (逆相)",
        "plot_invert_tooltip": "マイクの極性が逆相（180°反転）の場合、波形を上下反転して山と谷の向きを揃えます",
        "plot_full_view": "↔ 全体表示",
        "plot_full_tooltip": "チャープ信号全体のタイムラインを表示します",
        "plot_zoom_view": "🔍 拡大表示 (山谷確認)",
        "plot_zoom_tooltip": "波の山と谷の重なりを細かく確認できる拡大表示に切り替えます",
        "plot_legend_ref": "■ 基準音",
        "plot_legend_rec": "■ マイク音",
        "plot_waveform_title": "波形比較タイムライン (マウスホイールで拡大・ドラッグで移動可能)",
        "plot_waveform_xlabel": "時間",
        "plot_waveform_ylabel": "振幅",
        "plot_corr_title": "相互相関（一致度の検出ピーク）",
        "plot_corr_xlabel": "遅延ラグ",
        "plot_corr_ylabel": "相関係数",

        # Measurement & Apply Section
        "measure_group": "4. 測定実行 ＆ OBS反映",
        "mode_3_runs": "3回測定 (標準・おすすめ)",
        "mode_1_run": "1回測定 (クイック)",
        "mode_5_runs": "5回測定 (徹底検証・高信頼度)",
        "btn_start_measure": "測定開始（イヤホンをマイクに密着させてください）",
        "btn_measuring": "測定中 ({current}/{total} 回目)...",
        "detected_delay": "検出遅延: {delay:.1f} ms",
        "runs_history": "各回: {history} (中央値採用)",
        "single_run": "単発測定: {run}",
        "badge_perfect": "全測定が完全一致（ブレなし・確実）",
        "badge_max_diff_stable": "最大差: {diff:.1f}ms (極めて安定・高再現性)",
        "badge_max_diff_moderate": "最大差: {diff:.1f}ms (安定)",
        "badge_max_diff_noisy": "最大差: {diff:.1f}ms (環境音による乱れの可能性あり)",
        "badge_confidence": "信頼度: {conf}%",
        "badge_pending": "ばらつき: --",

        "btn_apply_measured": "⚡ 測定結果を反映 ({delay:.1f} ms)",
        "btn_apply_measured_unmeasured": "⚡ 測定結果を反映 (未測定)",
        "btn_applied_measured": "✓ 反映済み ({delay:.1f} ms)",
        "btn_apply_obs": "📥 OBS現在値 ({offset} ms)",
        "btn_apply_obs_none": "📥 OBS現在値 (--)",
        "btn_reset_zero": "0ms (生遅延)",
        "manual_trim": "オフセット微調整:",

        "obs_target_source": "反映先ソース:",
        "btn_fetch_obs": "📥 OBSから取得",
        "btn_fetch_obs_tooltip": "選択中のソースの現在の同期オフセット値をOBSから引き抜いて最新化します",
        "current_obs_val": "現在のOBS設定値: {offset} ms",
        "current_obs_none": "現在のOBS設定値: -- ms",
        "diff_needed": "(あと +{diff:.1f} ms 必要)",
        "diff_value": "(差分: {diff:+.1f} ms)",
        "diff_matched": "✓ OBSと完全一致中",
        "btn_apply_to_obs": "📤 測定結果をOBSに反映して返す",

        # Video source & Render Delay
        "obs_sync_video": "🎥 映像ソース（カラオケ/音ゲー画面等）にもレンダリング遅延を連動",
        "obs_video_target_source": "映像ソース:",
        "obs_no_video_sources": "映像ソースが見つかりません",
        "obs_not_connected_video_source": "OBS未接続 (映像ソース選択不可)",
        "current_video_delay_val": "現在の映像遅延: {delay} ms",
        "current_video_delay_none": "現在の映像遅延: なし (0 ms)",
        "warn_render_delay_limit": "※OBSの仕様上限（500ms）に合わせてクランプされます。",
        "status_applied_obs_with_video": "反映成功: 音声={audio_name}({audio_offset}ms), 映像={video_name}({video_offset}ms)",

        # Device & Status extras
        "device_rec_wasapi": "[推奨: WASAPI]",
        "device_compat_mme": "(互換用: MME)",
        "device_default": " [既定]",
        "status_device_refreshed": "オーディオデバイスを更新しました (再生: {out_count}件, 録音: {in_count}件)",
        "status_test_tone_played": "テスト確認音を再生しました。",
        "dialog_device_error_title": "デバイス取得エラー",
        "dialog_device_error_msg": "オーディオデバイス一覧の取得に失敗しました:\n{error}",
        "dialog_obs_connect_error_title": "OBS接続失敗",
        "dialog_obs_connect_error_msg": "OBS Studio (WebSocket v5) への接続に失敗しました。\n\n・OBSの [ツール] -> [WebSocketサーバー設定] で有効になっているか\n・ポート番号 ({port}) とパスワードが一致しているか\n\n詳細: {error}",

        # Dialogs
        "dialog_obs_unconnected_title": "OBS未接続",
        "dialog_obs_unconnected_msg": "先にOBS Studioに接続してください。",
        "dialog_confirm_apply_title": "OBS同期オフセットの反映",
        "dialog_confirm_apply_msg": "OBSの音声ソース 「{name}」 に設定値を返します。\n\n現在のOBS設定値: {current} ms\n新しく反映する値: {target} ms (差分: {diff})\n\nこの設定をOBSに書き戻してよろしいですか？",
        "dialog_confirm_apply_with_video_msg": "OBSの音声および映像ソースに設定値を反映します。\n\n【音声】 「{audio_name}」: {audio_target} ms\n【映像】 「{video_name}」: {video_target} ms (レンダリング遅延)\n{limit_note}\nこの設定をOBSに書き戻してよろしいですか？",
        "dialog_applied_title": "反映完了",
        "dialog_applied_msg": "OBSの「{name}」に {target} ms を書き戻しました！",
        "dialog_applied_with_video_msg": "OBSに設定を書き戻しました！\n\n・音声 「{audio_name}」: {audio_target} ms\n・映像 「{video_name}」: {video_target} ms (レンダリング遅延)",
        "dialog_apply_error_title": "適用エラー",
        "dialog_apply_error_msg": "OBSへのオフセット設定に失敗しました:\n{error}",
        "dialog_source_error_title": "ソース取得エラー",
        "dialog_source_error_msg": "OBS音声ソースの取得に失敗しました:\n{error}",
        "dialog_fetch_error_title": "取得エラー",
        "dialog_fetch_error_msg": "OBSからの設定値取得に失敗しました:\n{error}",
        "dialog_measure_error_title": "測定エラー",
        "dialog_measure_error_msg": "再生または録音中にエラーが発生しました:\n{error}",

        # AV Sync Verifier
        "btn_open_verifier": "🎧 同期検証 (AV Sync Check)",
        "btn_open_verifier_tooltip": "耳と目（OBSキャプチャ）で同期をリアルタイム検証するウィンドウを開きます",
        "verifier_title": "SyncTone - 同期検証 (AV Sync Checker)",
        "verifier_obs_hint": "💡 このウィンドウを OBS の「ウィンドウキャプチャ」で取り込むと、映像と音の同期を目視で確認できます",
        "verifier_mode_flash": "📺 視覚＆ビープ (AV Sync)",
        "verifier_mode_click": "🎵 聴感クリック (メトロノーム)",
        "verifier_play": "▶ 再生 (Space)",
        "verifier_stop": "⏹ 停止 (Space)",
        "verifier_tempo": "テンポ:",
        "verifier_volume": "音量:",
        "verifier_obs_trim": "OBS オフセット微調整:",
        "verifier_obs_current": "現在: {offset} ms",
        "verifier_target_source": "対象: {name}",
        "verifier_obs_not_connected": "OBS未接続",
        "verifier_flash_hint": "バーが中央 (0 ms) に重なった瞬間に光と音が完全一致するか確認します",
        "verifier_click_hint": "クリック音がダブらず（タ・タンと割れず）1つの音として聴こえるか確認します",
    },

    "en": {
        # Window & Header
        "app_title": "SyncTone - OBS Audio Sync Assistant",
        "lang_select": "Language:",
        "status_ready": "Ready: Connect to OBS and click Start Measurement.",
        "status_measuring": "Playing chirp tone (Total {total} runs)...",
        "status_sampling": "Measuring: Sampling {current} / {total} complete",
        "status_measured_auto": "Measurement finished: Automatically applied {delay:.1f} ms.",
        "status_measured_guide": "Measurement finished: Detected {delay:.1f} ms delay. Click '⚡ Apply Measured' to align peaks.",
        "status_applied_adj": "Applied {delay:.1f} ms to manual trim.",
        "status_reset_zero": "Reset manual offset to 0.0 ms (Raw).",
        "status_fetched_obs": "Applied OBS offset ({offset} ms) for '{name}' to preview. Waveform shift visible.",
        "status_applied_obs": "Applied successfully: {name} = {offset} ms returned to OBS.",
        "status_obs_loaded": "Loaded {count} audio sources from OBS.",
        "status_error": "An error occurred during measurement.",

        # OBS Section
        "obs_group": "1. OBS Studio Integration (WebSocket v5)",
        "obs_host_port": "Host/Port:",
        "obs_password": "Password:",
        "obs_password_placeholder": "Enter only if configured",
        "obs_connect": "Connect to OBS",
        "obs_disconnect": "Disconnect",
        "obs_connected": "● Connected",
        "obs_disconnected": "● Disconnected",
        "obs_no_sources": "No audio sources found",
        "obs_not_connected_source": "OBS Not Connected",
        "obs_recommended_source": "(Recommended: Backing Delay)",

        # Audio Section
        "audio_group": "2. Audio Devices && Volume",
        "audio_playback": "Playback (Earphones/Backing):",
        "audio_recording": "Recording (Target Mic):",
        "audio_volume": "Test Tone Volume:",
        "audio_test_tone": "Test Sound",
        "audio_test_tooltip": "Plays a short confirmation tone to check volume level",

        # Plot Section
        "plot_group": "3. Waveform & Alignment Visualizer",
        "plot_align": "Alignment Preview (Shifted)",
        "plot_align_tooltip": "Shifts the recorded waveform by detected delay to preview alignment",
        "plot_invert": "Invert Polarity (Phase Invert)",
        "plot_invert_tooltip": "Inverts recorded waveform 180° for out-of-phase microphones to align peaks",
        "plot_full_view": "↔ Full View",
        "plot_full_tooltip": "Shows the entire timeline of the chirp signal",
        "plot_zoom_view": "🔍 Zoom View (Peak Alignment)",
        "plot_zoom_tooltip": "Zooms in closely to inspect individual peaks and troughs",
        "plot_legend_ref": "■ Reference",
        "plot_legend_rec": "■ Mic Audio",
        "plot_waveform_title": "Waveform Timeline (Mouse wheel to zoom, drag to pan)",
        "plot_waveform_xlabel": "Time",
        "plot_waveform_ylabel": "Amplitude",
        "plot_corr_title": "Cross-Correlation (Delay Peak Detection)",
        "plot_corr_xlabel": "Delay Lag",
        "plot_corr_ylabel": "Correlation",

        # Measurement & Apply Section
        "measure_group": "4. Measurement & OBS Application",
        "mode_3_runs": "3 Measurements (Standard, Recommended)",
        "mode_1_run": "1 Measurement (Quick)",
        "mode_5_runs": "5 Measurements (Thorough Verification)",
        "btn_start_measure": "Start Measurement (Place earphones close to mic)",
        "btn_measuring": "Measuring ({current}/{total})...",
        "detected_delay": "Detected Delay: {delay:.1f} ms",
        "runs_history": "Runs: {history} (Median adopted)",
        "single_run": "Single run: {run}",
        "badge_perfect": "All measurements completely match (Zero jitter)",
        "badge_max_diff_stable": "Max diff: {diff:.1f}ms (Extremely stable)",
        "badge_max_diff_moderate": "Max diff: {diff:.1f}ms (Stable)",
        "badge_max_diff_noisy": "Max diff: {diff:.1f}ms (Possible ambient noise)",
        "badge_confidence": "Confidence: {conf}%",
        "badge_pending": "Jitter: --",

        "btn_apply_measured": "⚡ Apply Measured ({delay:.1f} ms)",
        "btn_apply_measured_unmeasured": "⚡ Apply Measured (Unmeasured)",
        "btn_applied_measured": "✓ Applied ({delay:.1f} ms)",
        "btn_apply_obs": "📥 OBS Value ({offset} ms)",
        "btn_apply_obs_none": "📥 OBS Value (--)",
        "btn_reset_zero": "0ms (Raw)",
        "manual_trim": "Offset Trim:",

        "obs_target_source": "Target Source:",
        "btn_fetch_obs": "📥 Fetch from OBS",
        "btn_fetch_obs_tooltip": "Fetches real-time sync offset of selected source from OBS",
        "current_obs_val": "Current OBS Offset: {offset} ms",
        "current_obs_none": "Current OBS Offset: -- ms",
        "diff_needed": "(+{diff:.1f} ms needed)",
        "diff_value": "(Diff: {diff:+.1f} ms)",
        "diff_matched": "✓ Exactly matches OBS",
        "btn_apply_to_obs": "📤 Apply Result to OBS",

        # Video source & Render Delay
        "obs_sync_video": "🎥 Link Render Delay to Video Source (Karaoke/Live Cam)",
        "obs_video_target_source": "Video Source:",
        "obs_no_video_sources": "No video sources found",
        "obs_not_connected_video_source": "OBS not connected (No video source)",
        "current_video_delay_val": "Current Video Delay: {delay} ms",
        "current_video_delay_none": "Current Video Delay: None (0 ms)",
        "warn_render_delay_limit": "* Clamped to OBS Render Delay limit (max 500ms).",
        "status_applied_obs_with_video": "Applied: Audio={audio_name} ({audio_offset}ms), Video={video_name} ({video_offset}ms)",

        # Device & Status extras
        "device_rec_wasapi": "[Recommended: WASAPI]",
        "device_compat_mme": "(Compat: MME)",
        "device_default": " [Default]",
        "status_device_refreshed": "Refreshed audio devices (Playback: {out_count}, Recording: {in_count})",
        "status_test_tone_played": "Played test confirmation tone.",
        "dialog_device_error_title": "Device Error",
        "dialog_device_error_msg": "Failed to get audio device list:\n{error}",
        "dialog_obs_connect_error_title": "OBS Connection Failed",
        "dialog_obs_connect_error_msg": "Failed to connect to OBS Studio (WebSocket v5).\n\n• Ensure WebSocket server is enabled in OBS: [Tools] -> [WebSocket Server Settings]\n• Verify port ({port}) and password\n\nDetails: {error}",

        # Dialogs
        "dialog_obs_unconnected_title": "OBS Not Connected",
        "dialog_obs_unconnected_msg": "Please connect to OBS Studio first.",
        "dialog_confirm_apply_title": "Apply OBS Sync Offset",
        "dialog_confirm_apply_msg": "Applying new sync offset to source '{name}':\n\nCurrent OBS value: {current} ms\nNew target value:  {target} ms (Diff: {diff})\n\nWrite this value back to OBS?",
        "dialog_confirm_apply_with_video_msg": "Applying settings to both OBS audio and video sources:\n\n[Audio] '{audio_name}': {audio_target} ms\n[Video] '{video_name}': {video_target} ms (Render Delay)\n{limit_note}\nWrite these settings back to OBS?",
        "dialog_applied_title": "Applied Successfully",
        "dialog_applied_msg": "Successfully updated sync offset for '{name}' to {target} ms in OBS!",
        "dialog_applied_with_video_msg": "Successfully applied to OBS!\n\n• Audio '{audio_name}': {audio_target} ms\n• Video '{video_name}': {video_target} ms (Render Delay)",
        "dialog_apply_error_title": "Apply Error",
        "dialog_apply_error_msg": "Failed to set sync offset in OBS:\n{error}",
        "dialog_source_error_title": "Source Error",
        "dialog_source_error_msg": "Failed to get audio sources from OBS:\n{error}",
        "dialog_fetch_error_title": "Fetch Error",
        "dialog_fetch_error_msg": "Failed to fetch offset from OBS:\n{error}",
        "dialog_measure_error_title": "Measurement Error",
        "dialog_measure_error_msg": "An error occurred during audio playback or recording:\n{error}",

        # AV Sync Verifier
        "btn_open_verifier": "🎧 AV Sync Checker",
        "btn_open_verifier_tooltip": "Open verification window to check sync with your eyes and ears via OBS capture",
        "verifier_title": "SyncTone - AV Sync Checker",
        "verifier_obs_hint": "💡 Add this window as a 'Window Capture' source in OBS to visually verify AV synchronization",
        "verifier_mode_flash": "📺 Visual & Beep (AV Sync)",
        "verifier_mode_click": "🎵 Auditory Click (Metronome)",
        "verifier_play": "▶ Play (Space)",
        "verifier_stop": "⏹ Stop (Space)",
        "verifier_tempo": "Tempo:",
        "verifier_volume": "Volume:",
        "verifier_obs_trim": "OBS Offset Trim:",
        "verifier_obs_current": "Current: {offset} ms",
        "verifier_target_source": "Target: {name}",
        "verifier_obs_not_connected": "OBS Disconnected",
        "verifier_flash_hint": "Verify that flash and beep trigger in perfect unison when the bar reaches center (0 ms)",
        "verifier_click_hint": "Listen to ensure the click sounds unified without flamming or doubling",
    },

    "ko": {
        # Window & Header
        "app_title": "SyncTone - OBS 오디오 싱크 어시스턴트",
        "lang_select": "언어 / Language:",
        "status_ready": "준비 완료: OBS를 실행하고 연결한 뒤 측정을 시작하세요.",
        "status_measuring": "차프 신호 재생 중 (총 {total}회)...",
        "status_sampling": "측정 중: {current} / {total} 회차 샘플링 완료",
        "status_measured_auto": "측정 완료: {delay:.1f} ms를 자동 반영했습니다.",
        "status_measured_guide": "측정 완료: {delay:.1f} ms 지연 검출. '⚡ 측정 결과 반영'을 누르면 파형이 일치합니다.",
        "status_applied_adj": "측정값 {delay:.1f} ms를 수동 조정에 반영했습니다.",
        "status_reset_zero": "수동 오프셋을 0.0 ms (생지연)로 초기화했습니다.",
        "status_fetched_obs": "OBS에서 '{name}'의 설정값 ({offset} ms)을 미리보기에 반영했습니다. 파형의 어긋남을 확인하세요.",
        "status_applied_obs": "반영 성공: {name} = {offset} ms를 OBS에 적용했습니다.",
        "status_obs_loaded": "OBS에서 {count}개의 오디오 소스를 불러왔습니다.",
        "status_error": "측정 중 오류가 발생했습니다.",

        # OBS Section
        "obs_group": "1. OBS Studio 연동 (WebSocket v5)",
        "obs_host_port": "호스트/포트:",
        "obs_password": "비밀번호:",
        "obs_password_placeholder": "설정한 경우에만 입력",
        "obs_connect": "OBS에 연결",
        "obs_disconnect": "연결 해제",
        "obs_connected": "● 연결됨",
        "obs_disconnected": "● 연결 안 됨",
        "obs_no_sources": "오디오 소스를 찾을 수 없습니다",
        "obs_not_connected_source": "OBS 미연결 (소스 선택 불가)",
        "obs_recommended_source": "(추천: 반주 지연)",

        # Audio Section
        "audio_group": "2. 측정용 장치 및 볼륨 설정",
        "audio_playback": "재생 (이어폰/반주 음원):",
        "audio_recording": "녹음 (대상 마이크 입력):",
        "audio_volume": "측정 볼륨:",
        "audio_test_tone": "볼륨 테스트",
        "audio_test_tooltip": "이어폰에서 짧은 확인음을 재생하여 볼륨을 확인합니다",

        # Plot Section
        "plot_group": "3. 측정 파형 및 일치도 시각화",
        "plot_align": "보정 미리보기 (겹치기)",
        "plot_align_tooltip": "검출된 지연만큼 이동하여 파형을 겹쳐서 확인합니다",
        "plot_invert": "위상 반전 보정 (역상)",
        "plot_invert_tooltip": "마이크가 역상(180° 반전)인 경우 파형을 상하 반전하여 피크 방향을 맞춥니다",
        "plot_full_view": "↔ 전체 보기",
        "plot_full_tooltip": "차프 신호 전체 타임라인을 표시합니다",
        "plot_zoom_view": "🔍 확대 보기 (피크 확인)",
        "plot_zoom_tooltip": "파형의 산과 골짜기 겹침을 세밀하게 확인하는 확대 화면으로 전환합니다",
        "plot_legend_ref": "■ 기준음",
        "plot_legend_rec": "■ 마이크음",
        "plot_waveform_title": "파형 비교 타임라인 (마우스 휠로 확대, 드래그로 이동 가능)",
        "plot_waveform_xlabel": "시간",
        "plot_waveform_ylabel": "진폭",
        "plot_corr_title": "상호 상관 (일치도 검출 피크)",
        "plot_corr_xlabel": "지연 래그",
        "plot_corr_ylabel": "상관 계수",

        # Measurement & Apply Section
        "measure_group": "4. 측정 실행 및 OBS 반영",
        "mode_3_runs": "3회 측정 (표준·추천)",
        "mode_1_run": "1회 측정 (빠른 측정)",
        "mode_5_runs": "5회 측정 (정밀 검증·높은 신뢰도)",
        "btn_start_measure": "측정 시작 (이어폰을 마이크에 밀착시켜 주세요)",
        "btn_measuring": "측정 중 ({current}/{total} 회차)...",
        "detected_delay": "검출 지연: {delay:.1f} ms",
        "runs_history": "각 회차: {history} (중앙값 채택)",
        "single_run": "단일 측정: {run}",
        "badge_perfect": "모든 측정이 완전 일치 (오차 없음·확실)",
        "badge_max_diff_stable": "최대 차이: {diff:.1f}ms (매우 안정·높은 재현성)",
        "badge_max_diff_moderate": "최대 차이: {diff:.1f}ms (안정)",
        "badge_max_diff_noisy": "최대 차이: {diff:.1f}ms (주변 소음 영향 가능성 있음)",
        "badge_confidence": "신뢰도: {conf}%",
        "badge_pending": "편차: --",

        "btn_apply_measured": "⚡ 측정 결과 반영 ({delay:.1f} ms)",
        "btn_apply_measured_unmeasured": "⚡ 측정 결과 반영 (미측정)",
        "btn_applied_measured": "✓ 반영 완료 ({delay:.1f} ms)",
        "btn_apply_obs": "📥 OBS 설정값 ({offset} ms)",
        "btn_apply_obs_none": "📥 OBS 설정값 (--)",
        "btn_reset_zero": "0ms (생지연)",
        "manual_trim": "오프셋 미세조정:",

        "obs_target_source": "반영할 소스:",
        "btn_fetch_obs": "📥 OBS 가져오기",
        "btn_fetch_obs_tooltip": "선택한 소스의 현재 동기화 오프셋 값을 OBS에서 실시간으로 가져옵니다",
        "current_obs_val": "현재 OBS 설정값: {offset} ms",
        "current_obs_none": "현재 OBS 설정값: -- ms",
        "diff_needed": "(앞으로 +{diff:.1f} ms 필요)",
        "diff_value": "(차이: {diff:+.1f} ms)",
        "diff_matched": "✓ OBS와 완전 일치 중",
        "btn_apply_to_obs": "📤 측정 결과를 OBS에 반영",

        # Video source & Render Delay
        "obs_sync_video": "🎥 비디오 소스(노래방/실사)에도 렌더링 지연 연동",
        "obs_video_target_source": "비디오 소스:",
        "obs_no_video_sources": "비디오 소스를 찾을 수 없습니다",
        "obs_not_connected_video_source": "OBS 미연결 (비디오 소스 선택 불가)",
        "current_video_delay_val": "현재 비디오 지연: {delay} ms",
        "current_video_delay_none": "현재 비디오 지연: 없음 (0 ms)",
        "warn_render_delay_limit": "* OBS 렌더링 지연 최대 제한(500ms)으로 제한됩니다.",
        "status_applied_obs_with_video": "반영 성공: 오디오={audio_name}({audio_offset}ms), 비디오={video_name}({video_offset}ms)",

        # Device & Status extras
        "device_rec_wasapi": "[추천: WASAPI]",
        "device_compat_mme": "(호환용: MME)",
        "device_default": " [기본값]",
        "status_device_refreshed": "오디오 장치를 갱신했습니다 (재생: {out_count}개, 녹음: {in_count}개)",
        "status_test_tone_played": "테스트 확인음을 재생했습니다.",
        "dialog_device_error_title": "장치 가져오기 오류",
        "dialog_device_error_msg": "오디오 장치 목록을 가져오지 못했습니다:\n{error}",
        "dialog_obs_connect_error_title": "OBS 연결 실패",
        "dialog_obs_connect_error_msg": "OBS Studio (WebSocket v5) 연결에 실패했습니다.\n\n• OBS의 [도구] -> [WebSocket 서버 설정]이 활성화되어 있는지 확인\n• 포트 번호 ({port})와 비밀번호가 일치하는지 확인\n\n상세 내용: {error}",

        # Dialogs
        "dialog_obs_unconnected_title": "OBS 미연결",
        "dialog_obs_unconnected_msg": "먼저 OBS Studio에 연결해 주세요.",
        "dialog_confirm_apply_title": "OBS 동기화 오프셋 반영",
        "dialog_confirm_apply_msg": "OBS 오디오 소스 '{name}'에 설정값을 적용합니다.\n\n현재 OBS 설정값: {current} ms\n새로 반영할 값:  {target} ms (차이: {diff})\n\n이 설정을 OBS에 적용하시겠습니까?",
        "dialog_confirm_apply_with_video_msg": "OBS 오디오 및 비디오 소스에 설정값을 반영합니다.\n\n[오디오] '{audio_name}': {audio_target} ms\n[비디오] '{video_name}': {video_target} ms (렌더링 지연)\n{limit_note}\n이 설정을 OBS에 적용하시겠습니까?",
        "dialog_applied_title": "적용 완료",
        "dialog_applied_msg": "OBS의 '{name}'에 {target} ms를 성공적으로 적용했습니다!",
        "dialog_applied_with_video_msg": "OBS에 성공적으로 반영되었습니다!\n\n• 오디오 '{audio_name}': {audio_target} ms\n• 비디오 '{video_name}': {video_target} ms (렌더링 지연)",
        "dialog_apply_error_title": "적용 오류",
        "dialog_apply_error_msg": "OBS 오프셋 설정에 실패했습니다:\n{error}",
        "dialog_source_error_title": "소스 오류",
        "dialog_source_error_msg": "OBS 오디오 소스를 가져오지 못했습니다:\n{error}",
        "dialog_fetch_error_title": "가져오기 오류",
        "dialog_fetch_error_msg": "OBS 설정값을 가져오지 못했습니다:\n{error}",
        "dialog_measure_error_title": "측정 오류",
        "dialog_measure_error_msg": "오디오 재생 또는 녹음 중 오류가 발생했습니다:\n{error}",

        # AV Sync Verifier
        "btn_open_verifier": "🎧 싱크 검증 (AV Sync Check)",
        "btn_open_verifier_tooltip": "OBS 윈도우 캡처를 통해 눈과 귀로 싱크를 실시간 검증하는 창을 엽니다",
        "verifier_title": "SyncTone - 싱크 검증기 (AV Sync Checker)",
        "verifier_obs_hint": "💡 OBS에서 이 창을 '윈도우 캡처'로 추가하면 화면과 소리의 일치 여부를 직접 확인할 수 있습니다",
        "verifier_mode_flash": "📺 시각 & 비프 (AV Sync)",
        "verifier_mode_click": "🎵 청각 클릭 (메트로놈)",
        "verifier_play": "▶ 재생 (Space)",
        "verifier_stop": "⏹ 정지 (Space)",
        "verifier_tempo": "템포:",
        "verifier_volume": "볼륨:",
        "verifier_obs_trim": "OBS 오프셋 미세조정:",
        "verifier_obs_current": "현재: {offset} ms",
        "verifier_target_source": "대상: {name}",
        "verifier_obs_not_connected": "OBS 미연결",
        "verifier_flash_hint": "바가 중앙(0 ms)을 지나는 순간 플래시와 비프음이 완벽히 일치하는지 확인하세요",
        "verifier_click_hint": "클릭음이 두 겹으로 갈라지지 않고 하나의 선명한 소리로 들리는지 확인하세요",
    },

    "zh_TW": {
        # Window & Header
        "app_title": "SyncTone - OBS 音訊同步小助手",
        "lang_select": "語言 / Language:",
        "status_ready": "就緒: 請啟動並連線至 OBS，然後開始測量。",
        "status_measuring": "正在播放線性調頻信號 (共 {total} 次)...",
        "status_sampling": "測量中: 第 {current} / {total} 次取樣完成",
        "status_measured_auto": "測量完成: 已自動套用 {delay:.1f} ms。",
        "status_measured_guide": "測量完成: 偵測到 {delay:.1f} ms 延遲。點擊「⚡ 套用測量結果」即可使波形完全重合。",
        "status_applied_adj": "已將測量值 {delay:.1f} ms 套用至手動微調。",
        "status_reset_zero": "已將位移重設為 0.0 ms (原始延遲)。",
        "status_fetched_obs": "已將 OBS「{name}」的設定值 ({offset} ms) 套用至預覽。可檢視波形重疊差異。",
        "status_applied_obs": "套用成功: 已將 {name} = {offset} ms 寫回 OBS。",
        "status_obs_loaded": "已從 OBS 載入 {count} 個音訊來源。",
        "status_error": "測量過程中發生錯誤。",

        # OBS Section
        "obs_group": "1. OBS Studio 串接 (WebSocket v5)",
        "obs_host_port": "主機/連接埠:",
        "obs_password": "密碼:",
        "obs_password_placeholder": "如有設定才需輸入",
        "obs_connect": "連線至 OBS",
        "obs_disconnect": "中斷連線",
        "obs_connected": "● 已連線",
        "obs_disconnected": "● 未連線",
        "obs_no_sources": "未找到音訊來源",
        "obs_not_connected_source": "OBS 未連線 (無法選擇音源)",
        "obs_recommended_source": "(推薦: 伴奏延遲)",

        # Audio Section
        "audio_group": "2. 測量用裝置與音量設定",
        "audio_playback": "播放 (耳機/伴奏音源):",
        "audio_recording": "錄音 (目標麥克風輸入):",
        "audio_volume": "測量音量:",
        "audio_test_tone": "音量試聽",
        "audio_test_tooltip": "從耳機播放簡短確認音以檢查音量大小",

        # Plot Section
        "plot_group": "3. 測量波形與一致性視覺化",
        "plot_align": "修正預覽 (重疊波形)",
        "plot_align_tooltip": "依據偵測到的延遲時間位移波形以預覽重疊效果",
        "plot_invert": "極性反轉修正 (反相)",
        "plot_invert_tooltip": "當麥克風為反相 (180° 反轉) 時，上下翻轉波形使波峰方向一致",
        "plot_full_view": "↔ 完整檢視",
        "plot_full_tooltip": "顯示線性調頻信號的完整時間軸",
        "plot_zoom_view": "🔍 放大檢視 (確認波峰波谷)",
        "plot_zoom_tooltip": "切換至高倍率放大檢視，精細確認波峰與波谷的重合程度",
        "plot_legend_ref": "■ 基準音",
        "plot_legend_rec": "■ 麥克風音",
        "plot_waveform_title": "波形對比時間軸 (滾輪縮放、拖曳平移)",
        "plot_waveform_xlabel": "時間",
        "plot_waveform_ylabel": "振幅",
        "plot_corr_title": "互相關 (一致度偵測峰值)",
        "plot_corr_xlabel": "延遲時間差 (Lag)",
        "plot_corr_ylabel": "相關係數",

        # Measurement & Apply Section
        "measure_group": "4. 執行測量與寫回 OBS",
        "mode_3_runs": "3次測量 (標準·推薦)",
        "mode_1_run": "1次測量 (快速)",
        "mode_5_runs": "5次測量 (精確驗證·高可靠度)",
        "btn_start_measure": "開始測量 (請將耳機緊貼麥克風)",
        "btn_measuring": "測量中 (第 {current}/{total} 次)...",
        "detected_delay": "偵測延遲: {delay:.1f} ms",
        "runs_history": "各次: {history} (採中位數)",
        "single_run": "單次測量: {run}",
        "badge_perfect": "所有測量完全一致 (零抖動·極精確)",
        "badge_max_diff_stable": "最大差值: {diff:.1f}ms (極度穩定·高再現性)",
        "badge_max_diff_moderate": "最大差值: {diff:.1f}ms (穩定)",
        "badge_max_diff_noisy": "最大差值: {diff:.1f}ms (可能受環境噪音干擾)",
        "badge_confidence": "可信度: {conf}%",
        "badge_pending": "抖動: --",

        "btn_apply_measured": "⚡ 套用測量結果 ({delay:.1f} ms)",
        "btn_apply_measured_unmeasured": "⚡ 套用測量結果 (未測量)",
        "btn_applied_measured": "✓ 已套用 ({delay:.1f} ms)",
        "btn_apply_obs": "📥 OBS 設定值 ({offset} ms)",
        "btn_apply_obs_none": "📥 OBS 設定值 (--)",
        "btn_reset_zero": "0ms (原始延遲)",
        "manual_trim": "位移微調:",

        "obs_target_source": "套用目標來源:",
        "btn_fetch_obs": "📥 從 OBS 讀取",
        "btn_fetch_obs_tooltip": "從 OBS 即時讀取所選音源目前的同步位移設定值",
        "current_obs_val": "目前 OBS 設定值: {offset} ms",
        "current_obs_none": "目前 OBS 設定值: -- ms",
        "diff_needed": "(尚需 +{diff:.1f} ms)",
        "diff_value": "(差值: {diff:+.1f} ms)",
        "diff_matched": "✓ 與 OBS 設定完全一致",
        "btn_apply_to_obs": "📤 將測量結果套用回 OBS",

        # Video source & Render Delay
        "obs_sync_video": "🎥 同步視訊來源（卡拉OK/實況）渲染延遲",
        "obs_video_target_source": "視訊來源:",
        "obs_no_video_sources": "未找到視訊來源",
        "obs_not_connected_video_source": "OBS 未連線 (無法選擇視訊來源)",
        "current_video_delay_val": "目前視訊延遲: {delay} ms",
        "current_video_delay_none": "目前視訊延遲: 無 (0 ms)",
        "warn_render_delay_limit": "※ 已依據 OBS 渲染延遲上限（500ms）進行限制。",
        "status_applied_obs_with_video": "套用成功: 音訊={audio_name}({audio_offset}ms), 視訊={video_name}({video_offset}ms)",

        # Device & Status extras
        "device_rec_wasapi": "[推薦: WASAPI]",
        "device_compat_mme": "(相容: MME)",
        "device_default": " [預設]",
        "status_device_refreshed": "已更新音訊裝置列表 (播放: {out_count} 個, 錄音: {in_count} 個)",
        "status_test_tone_played": "已播放測試確認音。",
        "dialog_device_error_title": "裝置取得錯誤",
        "dialog_device_error_msg": "取得音訊裝置列表失敗:\n{error}",
        "dialog_obs_connect_error_title": "OBS 連線失敗",
        "dialog_obs_connect_error_msg": "連線至 OBS Studio (WebSocket v5) 失敗。\n\n• 請確認 OBS 的 [工具] -> [WebSocket 伺服器設定] 是否已啟用\n• 請確認連接埠 ({port}) 與密碼是否正確\n\n詳細資訊: {error}",

        # Dialogs
        "dialog_obs_unconnected_title": "OBS 未連線",
        "dialog_obs_unconnected_msg": "請先連線至 OBS Studio。",
        "dialog_confirm_apply_title": "套用 OBS 同步位移",
        "dialog_confirm_apply_msg": "將把設定值寫回 OBS 音訊來源「{name}」。\n\n目前 OBS 設定值: {current} ms\n新套用的設定值: {target} ms (差值: {diff})\n\n確定要將此設定寫回 OBS 嗎？",
        "dialog_confirm_apply_with_video_msg": "將設定套用至 OBS 音訊與視訊來源：\n\n【音訊】 「{audio_name}」: {audio_target} ms\n【視訊】 「{video_name}」: {video_target} ms (渲染延遲)\n{limit_note}\n確定要將這些設定寫回 OBS 嗎？",
        "dialog_applied_title": "套用完成",
        "dialog_applied_msg": "已成功將 {target} ms 寫回 OBS 的「{name}」！",
        "dialog_applied_with_video_msg": "已成功套用至 OBS！\n\n• 音訊 「{audio_name}」: {audio_target} ms\n• 視訊 「{video_name}」: {video_target} ms (渲染延遲)",
        "dialog_apply_error_title": "套用錯誤",
        "dialog_apply_error_msg": "設定 OBS 同步位移失敗:\n{error}",
        "dialog_source_error_title": "來源取得錯誤",
        "dialog_source_error_msg": "取得 OBS 音訊來源失敗:\n{error}",
        "dialog_fetch_error_title": "讀取錯誤",
        "dialog_fetch_error_msg": "從 OBS 讀取設定值失敗:\n{error}",
        "dialog_measure_error_title": "測量錯誤",
        "dialog_measure_error_msg": "音訊播放或錄音過程中發生錯誤:\n{error}",

        # AV Sync Verifier
        "btn_open_verifier": "🎧 同步驗證 (AV Sync Check)",
        "btn_open_verifier_tooltip": "開啟驗證視窗，透過 OBS 視窗擷取以耳目雙重確認音訊延遲",
        "verifier_title": "SyncTone - 同步驗證器 (AV Sync Checker)",
        "verifier_obs_hint": "💡 在 OBS 中新增此視窗為「視窗擷取」，即可在預覽畫面上目視確認影音同步",
        "verifier_mode_flash": "📺 視覺與嗶聲 (AV Sync)",
        "verifier_mode_click": "🎵 聽覺節拍 (節拍器)",
        "verifier_play": "▶ 播放 (Space)",
        "verifier_stop": "⏹ 停止 (Space)",
        "verifier_tempo": "速度:",
        "verifier_volume": "音量:",
        "verifier_obs_trim": "OBS 偏移微調:",
        "verifier_obs_current": "目前: {offset} ms",
        "verifier_target_source": "目標: {name}",
        "verifier_obs_not_connected": "OBS 未連線",
        "verifier_flash_hint": "檢視游標通過中央 (0 ms) 時，閃爍與嗶聲是否完美同步",
        "verifier_click_hint": "聆聽節拍音是否凝聚為單一清晰聲響，無雙重重音現象",
    },

    "zh_CN": {
        # Window & Header
        "app_title": "SyncTone - OBS 音频同步助手",
        "lang_select": "语言 / Language:",
        "status_ready": "准备就绪: 请启动并连接 OBS，然后开始测量。",
        "status_measuring": "正在播放扫频信号 (共 {total} 次)...",
        "status_sampling": "测量中: 第 {current} / {total} 次采样完成",
        "status_measured_auto": "测量完成: 已自动应用 {delay:.1f} ms。",
        "status_measured_guide": "测量完成: 检测到 {delay:.1f} ms 延迟。点击“⚡ 应用测量结果”波形即可完全对齐。",
        "status_applied_adj": "已将测量值 {delay:.1f} ms 应用至手动微调。",
        "status_reset_zero": "已将偏移重置为 0.0 ms (原始延迟)。",
        "status_fetched_obs": "已将 OBS“{name}”的设置值 ({offset} ms) 应用至预览。可对比波形重叠差异。",
        "status_applied_obs": "应用成功: 已将 {name} = {offset} ms 写入 OBS。",
        "status_obs_loaded": "已从 OBS 加载 {count} 个音频源。",
        "status_error": "测量过程中发生错误。",

        # OBS Section
        "obs_group": "1. OBS Studio 联动 (WebSocket v5)",
        "obs_host_port": "主机/端口:",
        "obs_password": "密码:",
        "obs_password_placeholder": "如已设置请输入",
        "obs_connect": "连接 OBS",
        "obs_disconnect": "断开连接",
        "obs_connected": "● 已连接",
        "obs_disconnected": "● 未连接",
        "obs_no_sources": "未找到音频源",
        "obs_not_connected_source": "OBS 未连接 (无法选择音源)",
        "obs_recommended_source": "(推荐: 伴奏延迟)",

        # Audio Section
        "audio_group": "2. 测量设备与音量设置",
        "audio_playback": "播放 (耳机/伴奏音频):",
        "audio_recording": "录音 (目标麦克风输入):",
        "audio_volume": "测量音量:",
        "audio_test_tone": "音量试听",
        "audio_test_tooltip": "从耳机播放简短确认音以检查音量大小",

        # Plot Section
        "plot_group": "3. 测量波形与对齐可视化",
        "plot_align": "修正预览 (重叠波形)",
        "plot_align_tooltip": "根据检测到的延迟时间平移波形以预览对齐效果",
        "plot_invert": "极性反转修正 (反相)",
        "plot_invert_tooltip": "当麦克风为反相 (180° 反转) 时，上下翻转波形使波峰方向一致",
        "plot_full_view": "↔ 完整视图",
        "plot_full_tooltip": "显示扫频信号的完整时间轴",
        "plot_zoom_view": "🔍 放大视图 (确认波峰对齐)",
        "plot_zoom_tooltip": "切换至放大视图，精细确认波峰与波谷的重合对齐情况",
        "plot_legend_ref": "■ 基准音",
        "plot_legend_rec": "■ 麦克风音",
        "plot_waveform_title": "波形对比时间轴 (鼠标滚轮缩放、拖拽平移)",
        "plot_waveform_xlabel": "时间",
        "plot_waveform_ylabel": "振幅",
        "plot_corr_title": "互相关 (一致性检测峰值)",
        "plot_corr_xlabel": "延迟时差 (Lag)",
        "plot_corr_ylabel": "相关系数",

        # Measurement & Apply Section
        "measure_group": "4. 执行测量与写入 OBS",
        "mode_3_runs": "3次测量 (标准·推荐)",
        "mode_1_run": "1次测量 (快速)",
        "mode_5_runs": "5次测量 (深度验证·高可靠度)",
        "btn_start_measure": "开始测量 (请将耳机贴紧麦克风)",
        "btn_measuring": "测量中 (第 {current}/{total} 次)...",
        "detected_delay": "检测延迟: {delay:.1f} ms",
        "runs_history": "各次: {history} (取中位数)",
        "single_run": "单次测量: {run}",
        "badge_perfect": "所有测量完全一致 (零抖动·极准确)",
        "badge_max_diff_stable": "最大差值: {diff:.1f}ms (极度稳定·高重现性)",
        "badge_max_diff_moderate": "最大差值: {diff:.1f}ms (稳定)",
        "badge_max_diff_noisy": "最大差值: {diff:.1f}ms (可能受环境噪音干扰)",
        "badge_confidence": "置信度: {conf}%",
        "badge_pending": "抖动: --",

        "btn_apply_measured": "⚡ 应用测量结果 ({delay:.1f} ms)",
        "btn_apply_measured_unmeasured": "⚡ 应用测量结果 (未测量)",
        "btn_applied_measured": "✓ 已应用 ({delay:.1f} ms)",
        "btn_apply_obs": "📥 OBS 设置值 ({offset} ms)",
        "btn_apply_obs_none": "📥 OBS 设置值 (--)",
        "btn_reset_zero": "0ms (原始延迟)",
        "manual_trim": "偏移微调:",

        "obs_target_source": "目标音频源:",
        "btn_fetch_obs": "📥 从 OBS 获取",
        "btn_fetch_obs_tooltip": "从 OBS 实时提取所选音源当前的同步偏移设置值",
        "current_obs_val": "当前 OBS 设置值: {offset} ms",
        "current_obs_none": "当前 OBS 设置值: -- ms",
        "diff_needed": "(还需 +{diff:.1f} ms)",
        "diff_value": "(差值: {diff:+.1f} ms)",
        "diff_matched": "✓ 与 OBS 完全一致",
        "btn_apply_to_obs": "📤 将测量结果写入并返回 OBS",

        # Video source & Render Delay
        "obs_sync_video": "🎥 同步视频源（卡拉OK/实况）渲染延迟",
        "obs_video_target_source": "视频源:",
        "obs_no_video_sources": "未找到视频源",
        "obs_not_connected_video_source": "OBS 未连接 (无法选择视频源)",
        "current_video_delay_val": "当前视频延迟: {delay} ms",
        "current_video_delay_none": "当前视频延迟: 无 (0 ms)",
        "warn_render_delay_limit": "※ 已依据 OBS 渲染延迟上限（500ms）进行限制。",
        "status_applied_obs_with_video": "应用成功: 音频={audio_name}({audio_offset}ms), 视频={video_name}({video_offset}ms)",

        # Device & Status extras
        "device_rec_wasapi": "[推荐: WASAPI]",
        "device_compat_mme": "(兼容: MME)",
        "device_default": " [默认]",
        "status_device_refreshed": "已刷新音频设备列表 (播放: {out_count} 个, 录音: {in_count} 个)",
        "status_test_tone_played": "已播放测试确认音。",
        "dialog_device_error_title": "设备获取错误",
        "dialog_device_error_msg": "获取音频设备列表失败:\n{error}",
        "dialog_obs_connect_error_title": "OBS 连接失败",
        "dialog_obs_connect_error_msg": "连接 OBS Studio (WebSocket v5) 失败。\n\n• 请确认 OBS 的 [工具] -> [WebSocket 服务器设置] 是否已启用\n• 请确认端口 ({port}) 与密码是否匹配\n\n详细信息: {error}",

        # Dialogs
        "dialog_obs_unconnected_title": "OBS 未连接",
        "dialog_obs_unconnected_msg": "请先连接 OBS Studio。",
        "dialog_confirm_apply_title": "应用 OBS 同步偏移",
        "dialog_confirm_apply_msg": "将把设置值写回 OBS 音频源“{name}”。\n\n当前 OBS 设置值: {current} ms\n新应用的设置值: {target} ms (差值: {diff})\n\n确定要将此设置写入 OBS 吗？",
        "dialog_confirm_apply_with_video_msg": "将设置应用至 OBS 音频与视频源：\n\n【音频】 “{audio_name}”: {audio_target} ms\n【视频】 “{video_name}”: {video_target} ms (渲染延迟)\n{limit_note}\n确定要将这些设置写入 OBS 吗？",
        "dialog_applied_title": "应用完成",
        "dialog_applied_msg": "已成功将 {target} ms 写入 OBS 的“{name}”！",
        "dialog_applied_with_video_msg": "已成功应用至 OBS！\n\n• 音频 “{audio_name}”: {audio_target} ms\n• 视频 “{video_name}”: {video_target} ms (渲染延迟)",
        "dialog_apply_error_title": "应用错误",
        "dialog_apply_error_msg": "设置 OBS 同步偏移失败:\n{error}",
        "dialog_source_error_title": "音频源获取错误",
        "dialog_source_error_msg": "获取 OBS 音频源失败:\n{error}",
        "dialog_fetch_error_title": "获取错误",
        "dialog_fetch_error_msg": "从 OBS 获取设置值失败:\n{error}",
        "dialog_measure_error_title": "测量错误",
        "dialog_measure_error_msg": "音频播放或录音过程中发生错误:\n{error}",

        # AV Sync Verifier
        "btn_open_verifier": "🎧 同步验证 (AV Sync Check)",
        "btn_open_verifier_tooltip": "打开验证窗口，通过 OBS 窗口采集以耳目双重确认音频延迟",
        "verifier_title": "SyncTone - 同步验证器 (AV Sync Checker)",
        "verifier_obs_hint": "💡 在 OBS 中添加此窗口为“窗口采集”，即可在预览画面上目视确认音画同步",
        "verifier_mode_flash": "📺 视觉与哔声 (AV Sync)",
        "verifier_mode_click": "🎵 听觉节拍 (节拍器)",
        "verifier_play": "▶ 播放 (Space)",
        "verifier_stop": "⏹ 停止 (Space)",
        "verifier_tempo": "速度:",
        "verifier_volume": "音量:",
        "verifier_obs_trim": "OBS 偏移微调:",
        "verifier_obs_current": "当前: {offset} ms",
        "verifier_target_source": "目标: {name}",
        "verifier_obs_not_connected": "OBS 未连接",
        "verifier_flash_hint": "检查游标经过中央 (0 ms) 时，闪烁与哔声是否完全同步",
        "verifier_click_hint": "聆听节拍音是否融为单个清晰声音，无前后重音现象",
    }
}

class I18nManager:
    """Manages application language state and text translation."""

    _instance: Optional["I18nManager"] = None

    def __init__(self):
        self._current_lang: str = self.detect_system_lang()

    @classmethod
    def get_instance(cls) -> "I18nManager":
        if cls._instance is None:
            cls._instance = I18nManager()
        return cls._instance

    @staticmethod
    def detect_system_lang() -> str:
        """Detect language from OS locale."""
        sys_locale = QLocale.system().name().lower()
        if sys_locale.startswith("ja"):
            return "ja"
        elif sys_locale.startswith("ko"):
            return "ko"
        elif sys_locale.startswith("zh_tw") or sys_locale.startswith("zh_hk") or sys_locale.startswith("zh_mo") or "hant" in sys_locale:
            return "zh_TW"
        elif sys_locale.startswith("zh"):
            return "zh_CN"
        else:
            return "en"

    @property
    def current_lang(self) -> str:
        return self._current_lang

    @current_lang.setter
    def current_lang(self, lang: str) -> None:
        if lang in LANGUAGES:
            self._current_lang = lang

    def t(self, key: str, **kwargs: Any) -> str:
        """Translate key into current language with optional keyword formatting."""
        lang_dict = TRANSLATIONS.get(self._current_lang, TRANSLATIONS["en"])
        template = lang_dict.get(key, TRANSLATIONS["en"].get(key, key))
        if kwargs:
            try:
                return template.format(**kwargs)
            except Exception:
                return template
        return template


def t(key: str, **kwargs: Any) -> str:
    """Shortcut helper for translating strings."""
    return I18nManager.get_instance().t(key, **kwargs)
