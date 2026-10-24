# SyncTone Project Rules & Release Guidelines

このリポジトリ（`SyncTone`）で開発・ビルド・リリース作業を行う際、AIエージェントは以下のルールを**必ず厳守**してください。

---

## 1. リリース・タグプッシュ前の必須チェックリスト（最重要）

`git tag v*` の作成や GitHub へのリリース用プッシュ（`git push origin v*`）を行う前に、**必ずローカル環境で以下の手順をすべて実行し、ユーザー自身の動作確認（承認）を得てからプッシュすること。確認なしにタグをプッシュしてはならない。**

1. **バージョン番号と変更履歴（Changelog）の確認**
   - `pyproject.toml` および `src/synctone/__init__.py` のバージョン番号が一致していること。
   - `CHANGELOG.md`（英語）、`CHANGELOG.ja.md`（日本語）、`CHANGELOG.ko.md`（韓国語）の3ファイルが最新の内容および正しいリリース日付で更新されていること。

2. **ローカルでの全自動テスト実行**
   - `.\.venv\Scripts\pytest.exe tests/ -v` を実行し、全テストがパス（Exit code 0）することを確認する。
   - Windows オフスクリーン環境（`QT_QPA_PLATFORM=offscreen`）での終了時クラッシュを防ぐため、`pyqtgraph` の `exitCleanup=False` 設定および `tests/conftest.py` のセッション共通 `qapp` フィクスチャを維持すること。

3. **ローカルでの実行ファイル（`SyncTone.exe`）ビルドと起動確認**
   - **タグを切る前に必ずローカルで `.\.venv\Scripts\python.exe build.py` を実行し、`dist\SyncTone.exe` を生成する。**
   - 生成された `dist\SyncTone.exe` にモジュール不足（`ModuleNotFoundError`）がないか確認し、**ユーザーに `c:\develop\git\synctone\dist\SyncTone.exe` を実際に手元で起動・動作確認してもらい、「OK」の承認を得てから** タグの作成・プッシュに進むこと。

---

## 2. PyInstaller (`SyncTone.spec`) と `build.py` の注意事項

1. **標準ライブラリ・`scipy` サブパッケージを安易に `excludes` に入れない**
   - `SyncTone.spec` の `excludes` に Python 標準ライブラリ（`email`, `unittest`, `pydoc`, `http`, `xmlrpc` 等）や `scipy.*` サブパッケージ（`scipy.spatial`, `scipy.ndimage`, `scipy.interpolate` 等）を追加してはならない。
   - PyInstaller のランタイムフック（`pyi_rth_pkgres` / `pkg_resources`）や `scipy.signal` の内部インポートが起動時に失敗し、`.exe` 実行時のみ `ModuleNotFoundError` でクラッシュする原因となる。

2. **`build.py` 内で GUI 付きの `SyncTone.exe` を直接起動しない**
   - `build.py` は GitHub Actions のヘッドレス Windows ランナー（`windows-latest`）からも呼び出される。
   - PyInstaller で固めた `SyncTone.exe`（`console=False`）を CI 上で起動すると、ヘッドレス環境でイベントループやダイアログ待ちが発生して CI ジョブが無限ハングするため、`build.py` の中では `.exe` の起動を行わないこと。

---

## 3. 多言語対応（i18n）と UI 設計のルール

1. **5言語の同期更新**
   - UI テキストを追加・変更する場合は、`src/synctone/i18n.py` 内の5言語すべて（`ja`, `en`, `ko`, `zh_TW`, `zh_CN`）の辞書キーを漏れなく追加・更新すること。
2. **手動オフセット値の保護**
   - 測定完了時（`_on_measurement_finished`）に、ユーザーが調整中の手動オフセット値（`spin_offset` / `slider_offset`）を自動で上書きしてはならない。測定結果の反映はユーザーが明示的に「測定結果を反映」ボタンを押したときのみ行うこと。
