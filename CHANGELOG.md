# 更新履歴 (CHANGELOG)

## [2.1.0] - 2026-08-24

### 🚀 新機能 & 改善 (New Features & Fixes)
- **ストリーム映像へのQRコード・URL上書き表示（QR Code Overlay）**:
  - **動画・写真共通の統合設定**:
    - 設定スイッチを1本化（`overlay_qr_enabled`）し、1クリックで動画・写真・待機画面のQRオーバーレイを一括制御可能に。
  - **フル画面オーバーレイの見切れ自動解消**:
    - YouTube動画の解像度（720p, 480p, 1080p等）に合わせてオーバーレイ画像を自動スケーリングし、画面端の見切れを根本防止。
  - **待機画面共通の構造 & URL完全表記（手入力対応）**:
    - QRコードに加え、手入力アクセスが可能なよう完全なWeb Request URL（Full URL）を一切省略せずに明瞭表記。
  - **表示レイアウトモード（コンパクト / フル画面）**:
    - **右下コンパクトモード (Compact / デフォルト)**: 映像右下に 260x260px の角丸白カード（QRコード＋完全URL）を表示。
    - **フル画面モード (Fullscreen)**: 待機画面と同じ大画面レイアウト（中央大QRコード＋タイトル＋完全URL）で映像上にオーバーレイ表示。
  - **シームレス・ホットリロード**:
    - 動画や写真の再生中であっても、設定保存時に再生位置（経過秒数）を自動維持したまま即座に画面上の表示が切り替わるよう改善。

## [2.0.1] - 2026-08-24

### 🔄 ロールバック & プロセスライフサイクル安定化 (Rollback & Process Lifecycle Fix)
- **安定版コードベースへのロールバック**:
  - 実験的機能（写真フレームフィーダー・QRオーバーレイ）を一時巻き戻し、検証済みの安定版（v2.0.0 ベース）に復元。
- **子プロセス終了処理の完全強化**:
  - アプリ終了時に `cloudflared.exe`、`ffmpeg.exe` および標準入力パイプを確実に即時強制終了（`kill_proc`）するよう修正。
  - バックグラウンドでのゾンビプロセスの残存と、それに起因する一時フォルダロックや Cloudflare Quick Tunnel の多重接続（HTTP 429 / Code 1015）を根本防止。

## [2.0.0] - 2026-08-22

### 🚀 新機能 (New Features)

#### 1. ヘッドレス動作モード & HTTP API サーバー対応
- `--headless` / `-hl` 引数を指定して、GUIを表示せずにバックグラウンドのAPIサーバーとして起動可能になりました。
- 外部アプリケーション（VRCBeaconやVue 3フロントエンド等）からHTTP JSON API経由でストリーマーの全機能を遠隔操作可能になりました。
- 全エンドポイントで **CORS (`Access-Control-Allow-Origin: *`)** に完全対応。
- **実装されたAPIエンドポイント**:
  - `GET /api/status`: ストリーマー状態、トンネルURL、再生中動画、キュー一覧、ループ/シャッフル状態を取得
  - `POST /api/queue`: 動画またはプレイリストURLの追加
  - `POST /api/control`: 再生操作（`skip`, `clear_queue`, `stop`, `delete_item`, `move_item`, `shuffle`, `set_loop`, `set_shuffle`）
  - `POST /api/shutdown`: サーバーおよびバックグラウンドプロセスの正常終了
  - `GET /api/config` / `POST /api/config`: 設定の取得および動的更新
  - `GET /` / `GET /stream.m3u8` (ブラウザアクセス時): HLS Web Player HTML配信

#### 2. 設定機能 & 設定画面 (Settings UI & config.json)
- GUI右上に「⚙ Settings」ボタンを追加し、専用の設定モーダルダイアログから以下の項目を変更・永続保存できるようになりました：
  - **サーバーポート (Server Port)**: APIおよびHLS配信ポート（デフォルト: `8000`）
  - **HLSセグメント秒数 / バッファ秒数 (HLS Segment Duration)**: ffmpeg `-hls_time`（デフォルト: `3` 秒）
  - **動画切り替え待機秒数 (Transition Wait Duration)**: 動画終了後のバッファ再生完了待機時間（デフォルト: `5` 秒）
  - **Web Player Live Sync Count**: Web Playerの初期同期バッファ数（デフォルト: `4`）
  - **Loop Queue / Shuffle Play のデフォルトON/OFF設定**
- 設定画面内に**折りたたみ式の「API 仕様・引数リファレンス」**を内蔵。

#### 3. シャッフル再生 & キュー保持ループ再生 (Shuffle & Repeat Playback)
- **即時シャッフル (Shuffle List / Now)**:
  - 「🔀 Shuffle List」ボタンまたは `POST /api/control` (`{"action": "shuffle"}`) で現在のキューを一瞬でランダムに並び替え。
- **シャッフル再生モード (Shuffle Mode)**:
  - 「🔀 Shuffle」スイッチまたは `POST /api/control` (`{"action": "set_shuffle", "enabled": true}`) で、キューから次に再生する曲をランダムに選出。
- **キュー保持ループ再生モード (Loop / Repeat Queue)**:
  - 「🔁 Loop」スイッチまたは `POST /api/control` (`{"action": "set_loop", "enabled": true}`) で有効化。
  - 再生終了（またはスキップ）した動画をキューの末尾へ自動的に再登録し、キューを枯渇させずにエンドレスループ再生。
  - シャッフルとループの併用で「登録動画群のランダムエンドレス再生」が可能。

#### 4. キューのドラッグ＆ドロップ並び替え & オートスクロール (DnD Reordering & Auto-scroll)
- **ドラッグ＆ドロップ並び替え**:
  - 各行のグリップアイコン「`☰`」または動画タイトルをドラッグして直感的に順序を変更可能。
  - ドラッグ中に対象行および移動先プレビューがハイライト表示。
  - 従来の「`▲`」「`▼`」ボタンも維持し、両立して操作可能。
- **自動スクロール (Auto-scroll)**:
  - ドラッグ中にカーソルをキューリストの上端付近または下端付近に持っていくと、リストが自動的に上下へ滑らかにスクロール。

---

### 🛠 内部設計・リファクタリング (Architecture & Refactoring)
- **モジュール分離**:
  - `streamer_core.py`: ストリーミングエンジン、キュー管理、プロセス制御、設定永続化
  - `api_server.py`: Python標準 `http.server` ベースのマルチスレッドCORS APIサーバー
  - `gui_streamer.py`: CLI引数解析、ヘッドレスモード制御、CustomTkinter GUI
- **外部依存の極小化**:
  - APIサーバーはPython標準ライブラリ（`http.server`, `socketserver`, `json`）のみで構築し、PyInstallerでの単一EXEビルド安定性と軽量性を維持。
