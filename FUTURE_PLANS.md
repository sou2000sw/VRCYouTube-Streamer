# 🔮 将来の機能拡張案・バックログ (Future Ideas & Backlog)

本ドキュメントは、VRCYouTube Streamer のバージョンアップ計画、タスク進捗状況、および将来の設計案を記録するバックログです。

---

## 📋 タスク進捗一覧・ステータス表 (Roadmap & Implementation Status)

| No. | カテゴリ | タスク名 / 機能概要 | バージョン | 状態 |
| :---: | :--- | :--- | :---: | :---: |
| **1** | 📻 ラジオ機能 | **YouTubeサムネイル＆ラジオ番組風カード画面の自動生成** (Radio Card Visualizer) | v2.2.0 | 🟢 **実装完了 ✅** |
| **2** | 🔒 セキュリティ | **Webリモコンのパスワード/PIN認証保護機能** (Password Protection) | v2.3.0 | 🟢 **実装完了 ✅** |
| **3** | 🔀 キュー操作 | **キューの表示専用ソート＆種別絞り込み機能** (Display Sort & Filtering) | v2.3.0 | 🟢 **実装完了 ✅** |
| **4** | 📊 帯域・診断 | **配信ビットレート・遅延・FPSのリアルタイム診断表示** (Diagnostics Dashboard) | v2.4.0 | 🟢 **実装完了 ✅** |
| **5** | 📱 UI/統合 | **スマホ向け写真・スクショ一括アップロード機能** (Batch Photo Upload) | v2.4.0 | 🟢 **実装完了 ✅** |
| **6** | 🖼️ 背景選択 | **BGM/ラジオモード時の背景切り替え機能** (Radio Background Selector) | v2.5.0 | 🟢 **実装完了 ✅** |
| **7** | 🎬 互換性 | **実機検証済み対応動画元・プラットフォームの仕様明記** (Platform Compatibility) | v2.5.0 | 🟢 **実装完了 ✅** |
| **8** | 🧩 プラグイン | **Webリモコン＆VRCBeaconプラグインUIの完全統合＆UI正本配置整理** (Integrated UI) | v2.6.0 | 🟢 **実装完了 ✅** |
| **9** | 📻 モード分離 | **再生モード3分岐 ＆ 写真・動画キュー完全分離 ＆ スライドショー安定化** (Playback Modes) | **v2.7.0** | 🟢 **実装完了 ✅** |
| **10** | 📱 QRオーバーレイ | **待機画面・通常動画・ラジオ全画面でのQRコード表示モード統括・修正** (QR Overlay) | **v2.7.0** | 🟢 **実装完了 ✅** |
| **11** | ⏰ 時計表示 | **配信実時刻（LIVE時計）オーバーレイ機能の修正・堅牢化** (Live Clock Overlay) | 次期予定 | 🟡 **要対応 ⚠️** |

---

## 1. 📻 YouTubeサムネイル＆ラジオ番組風カード画面の自動生成 (Radio Card Visualizer) 【実装完了 ✅】

### 概要
BGM/ラジオモード再生時、YouTubeから取得したサムネイル画像（アルバムアート風）と動画タイトル・アーティスト情報を1枚の洗練された **「1920x1080 ラジオ番組風カード画面」** として自動合成・生成する機能。

### 実装設計
1. **背景レイヤー**:
   - YouTubeサムネイルを拡大＋ガウスぼかし（Gaussian Blur）し、ダーク調のグラデーション・オーバーレイを重ねたリッチで落ち着いた背景
2. **左側（アルバムアート領域）**:
   - `yt-dlp` で取得した高画質サムネイル（`maxresdefault` / `hqdefault` / `webp` / `jpg`）
   - 角丸（Corner Radius）＋繊細なドロップシャドウ/ボーダー
3. **中央〜右側（楽曲情報領域）**:
   - 楽曲タイトル（Bold、日本語フォント自動解決: `meiryo.ttc` / `msgothic.ttc` / `arial.ttf`）
   - アーティスト名 / チャンネル名の明瞭なタイポグラフィ
   - ※波形イコライザー・QRコード・シークバーは除外し、超低負荷＆余計な外部アクセス・ズレのないシンプルなアルバムカードデザインを採用
4. **極小帯域配信の維持**:
   - 静止画（PIL合成）として生成し、FFmpegで超低帯域（`libx264` 200kbps, 2fps）＋AAC音声（128kbps）でエンコード。
   - 合計ビットレート約300kbpsのまま、高画質・高音質・バッファ詰まりゼロの配信を実現。
5. **高速キャッシュ**:
   - `hls_output/images/radio_cache/` に動画IDごとに保存し、次回以降即時ロード。

---

## 2. 🔒 Webリモコンのパスワード/PIN認証保護機能 (Web Remote Password Protection) 【実装完了 ✅】

### 概要
Webリモコン（スマホブラウザ等）に簡単なパスワード（数字4〜6桁のPINコードや文字列）を設定し、パスワードを知っているユーザーのみがリモコン画面の閲覧・操作を行えるようにする機能。
不特定多数からのアクセスや定期ポーリング（`/api/status`）によるホストPCのCPU/ネットワーク負荷を防ぐ。

### 仕様・動作フロー
1. **ホスト側の設定**:
   - `config.json` に `"web_password": ""`（デフォルト: 空文字列＝認証なし）。
   - GUI（`gui_streamer.py`）の設定画面に「Webリモコン パスワード」入力欄を追加。
   - 空欄の場合は従来通り誰でもアクセス可能（オプトイン設計）。
   - ホスト本人（localhost / ループバック）からのアクセスは常に認証不要（パスワード入力なしで全操作可能）。

2. **ゲストのアクセスフロー（スマホ / PCブラウザ）**:
   - `web_password` が設定されている場合：
     1. Webリモコン画面（`/`）を開くと、操作UIを隠した状態で「パスワード入力モーダル（PIN入力）」を表示。
     2. **モーダル表示中は `/api/status` の定期ポーリングを完全停止**（ホスト負荷ゼロを維持）。
     3. 正しいパスワードを入力すると、ブラウザのセッション（`sessionStorage`）に記憶して通常のリモコン画面を開く。
        - **タブを閉じる、または次回ソフト起動（新URL発行）で自動消滅**（長期間残り続けない安全設計）。
        - 同一タブ内でのリロード時は再入力不要。
     4. 誤ったパスワードの場合は「パスワードが違います」と表示してブロック。
     5. UI内に「ログアウト（認証情報クリア）」ボタンを配置。

3. **サーバー側（API）の負荷・セキュリティ対策**:
   - ゲストからの全APIリクエスト（`/api/status`, `/api/queue`, `/api/control`, `/api/upload` 等）について、リクエストヘッダー（`X-Web-Password`）を検証。
   - 未認証またはパスワード不一致の場合、キュー処理やシリアライズを行わず **即座に `401 Unauthorized` を返却**。
   - ※**VRChat内の動画プレイヤー（`/stream.m3u8`, `*.ts`）は認証対象外**とし、プレイヤー側への影響なくストリーム再生を維持。

### 変更対象予定ファイル
- `streamer_core.py`（デフォルト設定 `web_password: ""` の追加、ステータスデータに `has_web_password: bool` を含める）
- `config.dist.json`（配布用設定テンプレートへの追加）
- `api_server.py`（`X-Web-Password` ヘッダー検証、401返却、認証除外パスのハンドリング）
- `ui/index.html`（パスワード入力モーダルUI、ローカルストレージ保存、APIリクエストヘッダー付与、ポーリング制御）
- `gui_streamer.py`（ホストGUI設定画面にパスワード入力欄を追加）

---

## 3. 🔄 外部ソース（yt-dlp等）の自動更新・メンテナンス機能 (External Tools Auto-Update & Maintenance) 【検討中 📋】

### 概要
YouTube側のプレイヤー仕様変更や暗号化シグネチャ変更（n-sig/JSチャレンジ/PO-Token等）に伴い、動画・音楽の解析・抽出ができなくなる問題を防止するため、`yt-dlp` 等の外部依存バイナリをアプリ本体の再インストールなしで自動的またはワンクリックで最新版へ更新できる機能。

### 背景と課題
- **現状**: `yt_dlp` は PyInstaller によって `VRCYouTubeStreamer.exe` の内部に静的バンドルされている。
- **課題**: YouTube側の仕様変更により再生不能になった場合、アプリ全体のリビルドおよび新バージョンの再配布・全ユーザーによる再ダウンロードが必要となり、ダウンタイムと保守負担が大きい。

### 仕様・実装設計
1. **外部バイナリ（`yt-dlp.exe`）方式への移行**:
   - `ffmpeg.exe` と同様に、アプリ同階層（または `bin/`）に独立した `yt-dlp.exe` を同梱・配置。
   - `streamer_core.py` の URL 展開・メタデータ取得処理を `yt-dlp.exe` の CLI（JSON出力 `--dump-single-json`）呼び出しに移行、または外部バイナリ優先参照とする。
   - アプリ本体の EXE サイズ削減にも寄与。

2. **更新トリガー**:
   - **① 起動時バックグラウンド自動チェック**:
     - `config.json` の `"auto_update_ytdlp": true`（既定値: 有効）に基づき、起動時に非同期スレッドで最新版の有無を確認・自動更新（起動処理をブロックしない）。
   - **② Webリモコン / GUI からの手動ワンクリック更新**:
     - Web リモコン UI の設定画面およびデスクトップ GUI に「yt-dlp を更新」ボタンを設置。
     - 更新進捗（ダウンロード中・完了・最新です 等）をトースト通知やステータスログに表示。
   - **③ 再生エラー時の自動リカバリ試行**:
     - YouTube ストリーム取得時に特定のエラー（ExtractorError, HTTP 403, Sign in required 等）を検知した場合、バックグラウンドで `yt-dlp.exe -U` を試行して再取得を試みる。

3. **他コンポーネントの更新ポリシー**:
   - `yt-dlp`: 頻繁な更新が必要なため自動/手動更新を実装。
   - `ffmpeg.exe`: 安定しており大容量（~80MB）なため、自動更新は行わず同梱版を固定利用。
   - `cloudflared.exe`: 安定しているため現状の管理を維持。
   - `VRCYouTubeStreamer 本体`: GitHub Releases API を照会し、「最新バージョン vX.X.X が公開されています」の通知のみ表示。

### 変更対象予定ファイル
- `streamer_core.py`（外部 `yt-dlp.exe` 呼び出し、JSONパース、`-U` 実行/更新マネージャー、エラー時のリカバリ処理）
- `api_server.py`（`/api/system/update_ytdlp` エンドポイント、バージョン情報の返却）
- `build_exe.py`（`yt-dlp.exe` の配布パッケージ同梱処理、PyInstaller からのモジュール除外最適化）
- `config.dist.json`（`auto_update_ytdlp: true` 設定項目の追加）
- `gui_streamer.py`（設定タブに yt-dlp バージョン表示＆「今すぐ更新」ボタン追加）
- `ui/index.html`（Webリモコン設定モーダルに更新ボタン＆バージョン表示追加）
- `README.md` / `README.txt`（構成ファイルの説明に `yt-dlp.exe` を追加）

---

## 4. 🎨 ホストソフトGUIのモダン化・リデザイン (Host Software GUI Modernization) 【検討中 📋】

### 概要
現行の CustomTkinter ベースのデスクトップホスト画面（`gui_streamer.py`）を、Webリモコンと同等以上の洗練されたモダンデザイン・操作性（サイドバーナビゲーション、リアルタイム配信プレビュー、直感的なドラッグ＆ドロップキュー操作、Windows 11 親和性等）へと刷新する検討案。

### 現状と課題
- **現状**: `customtkinter` によるダークテーマUIを採用しているが、画面内にコントロール・URL・QRコード・ログが縦積みに密集しており、機能追加に伴って設定ウィンドウ等への動線が複雑化している。
- **課題**:
  - Webリモコン（スマホブラウザ向けUI）の洗練されたデザインとホストデスクトップUIにギャップがある。
  - 配信中の映像/カード画面のローカルプレビュー機能がない。
  - キューの直感的なドラッグ＆ドロップ並び替えや、複数ファイルの一括投入が難しい。

### 検討アプローチ
1. **アプローチA: WebView2 / pywebview による Web 技術統合（★ 推奨）**:
   - ホスト画面も Web 技術（HTML/CSS/JS または React/Tailwind 等）でレンダリングし、Windows 標準の WebView2 ランタイム経由で表示。
   - **メリット**: Web リモコンとデザイン資産・コンポーネントを共通化でき、超美麗なアニメーション・グラスモーフィズム・配信プレビュー（`<video>` タグでの HLS 再生）が容易に実現可能。
2. **アプローチB: CustomTkinter の全面レイアウト刷新（軽量維持）**:
   - Python 標準の依存関係を保ちつつ、レイアウトを「サイドバー（ナビゲーション）＋メインパネル（プレビュー＆キュー）＋右サイド（QR・ステータス）」の3ペイン構成に再構築。
   - **メリット**: 新たな依存ライブラリの追加が不要で、既存の PyInstaller ビルド構成を維持可能。
3. **アプローチC: PyQt6 / PySide6 / PyQt-Fluent-Widgets（ネイティブ Fluent Design）**:
   - Windows 11 の Mica / Acrylic マテリアルにネイティブ適合したデスクトップUI。

### 導入したい新機能・UX改善案
- **📺 リアルタイム配信プレビュー**: ホスト画面上で現在 VRChat 向けに送出されている映像（動画/ラジオカード/写真）を常時モニタリング。
- **🎛️ サイドバーナビゲーション**:
  - `Now Playing` (現在再生中・プレイヤー操作)
  - `Queue Manager` (ドラッグ＆ドロップ並び替え・検索・一括追加)
  - `Media Library` (写真・待機画像の管理)
  - `Settings` (タブ別・カテゴリ別に整理された設定)
  - `Logs & Diagnostics` (リアルタイムログ・接続状況)
- **📊 リアルタイムステータスパネル**:
  - 接続中のゲスト数、Cloudflare Tunnel 状態（Latency / URL）、CPU負荷、エンコードFPS等のビジュアルメーター。
- **📂 ドラッグ＆ドロップ対応**:
  - 動画ファイルや画像ファイルをホストウィンドウにドラッグ＆ドロップするだけでキューに即追加。

---

## 5. 🎵 ラジオモード時のクロスフェード・滑らか切り替え (Smooth Crossfade in Radio Mode) 【実装予定 📝】

### 概要
ラジオモード（音声＋アルバムアートカード/スライドショー）再生時、曲の終了と次の曲の開始がブツ切り・無音にならず、設定した秒数（例: 2〜4秒）で前の曲をフェードアウトしながら次の曲をフェードインして滑らかにシームレス遷移する機能。

### 仕様・実装設計
1. **先読み（prefetch）との連携**:
   - 既に実装されている `prefetch_item` により次曲のオーディオストリームURLは事前取得済み。
   - 再生中の曲の終了残り \(N\) 秒（クロスフェード秒数）のタイミングで次曲のエンコード・音声結合処理を起動。
2. **クロスフェード処理方式**:
   - **方式A (FFmpeg `acrossfade` / `afade` フィルター)**:
     - 曲末尾と曲頭のオーディオストリームを `acrossfade=d=3:c1=tri:c2=tri` 等でオーバーラップ合成し、HLS セグメントシーケンス番号（`sequence_offset`）の連続性を維持して送出。
   - **方式B (セグメントレベル・ボリュームカーブ合成)**:
     - 前曲末尾セグメントに `volume='1.0-t/d':eval=frame`、次曲頭セグメントに `volume='t/d':eval=frame` を適用してシームレスに結合。
3. **設定とUI**:
   - `config.json`: `"radio_crossfade_duration": 3`（0で無効、1〜5秒で調整可能）。
   - Webリモコン / ホスト設定画面に「クロスフェード秒数」スライダーを追加。

### 変更対象予定ファイル
- `streamer_core.py`（クロスフェード用オーディオ合成ロジック、セグメント遷移ハンドリング）
- `config.dist.json`（`radio_crossfade_duration: 3` 追加）
- `gui_streamer.py` / `ui/index.html`（クロスフェード設定UI）

---

## 6. ⚡ FFmpeg ハードウェアエンコード（NVENC / QSV / AMF）対応 (Hardware-Accelerated Video Encoding) 【実装予定 📝】

### 概要
ホストPCで通常動画モード（1080p60 / 720p60）を高画質配信する際、CPU負荷を大幅に低減し、省電力かつ高フレームレート・低遅延を維持するため、GPUによるハードウェアエンコード（NVIDIA NVENC, Intel QSV, AMD AMF）を自動検出・選択可能にする機能。

### 仕様・実装設計
1. **対応エンコーダー**:
   - `auto` (自動検出: NVENC → QSV → AMF → `libx264` ソフトウェアフォールバック)
   - `h264_nvenc` (NVIDIA GeForce / Quadro / RTX)
   - `h264_qsv` (Intel Core CPU 内蔵 Iris Xe / UHD Graphics / Arc)
   - `h264_amf` (AMD Radeon)
   - `libx264` (CPU ソフトウェアエンコード、高互換性)
2. **自動検出（Probe）機構**:
   - アプリ起動時に `ffmpeg -encoders` を実行し、ホスト環境で利用可能なエンコーダーを自動チェック・キャッシュ。
   - GPUエンコーダーが使用不可・エラーを返した場合は、自動的に安全な `libx264` へフォールバック。
3. **モード別の最適化**:
   - **通常動画モード**: 指定された GPU エンコーダー（NVENC/QSV/AMF）を使用して高速・低負荷エンコード。
   - **ラジオモード**: 静止画＋音声のため、従来通り極小帯域（2fps / 200kbps）の `libx264` で超軽量稼働。
4. **設定とUI**:
   - `config.json`: `"video_encoder": "auto"`
   - Webリモコン設定モーダル / ホスト設定画面に「動画エンコーダー（自動 / CPU / NVENC / QSV / AMF）」選択セレクトボックスを追加。

### 変更対象予定ファイル
- `streamer_core.py`（エンコーダー自動プローブ関数、FFmpeg 引数生成ロジックの動的切替）
- `config.dist.json`（`video_encoder: "auto"` 追加）
- `gui_streamer.py` / `ui/index.html`（エンコーダー選択UI）

---

## 7. 🛠️ CLI 引数・環境設定オーバーライド機構の総点検・堅牢化 (CLI Arguments & Config Overrides Overhaul) 【実装予定 📝】

### 概要
CLI 引数（`--port`, `--host`, `--no-tunnel`, `--resolution`, `--bitrate` 等）や `StreamerCore` 初期化時のオーバーライド引数（`override_port`, `override_host`, `override_enable_tunnel` 等）が、設定ファイル（`config.json`）の読み込み・保存や GUI / Web API（`/api/config`）からの動的設定更新と干渉し、CLI による一時指定が意図せず上書きされたり無効化される問題の総点検と再設計。

### 現状と課題
- **設定優先順位の曖昧さ**: `load_config()` や `update_config()` の実行時に、CLI で指定されたオーバーライド値が `config.json` の値で上書きされたり、逆に一時的な CLI 指定値が `config.json` に永続保存されてしまうリスクがある。
- **対応パラメータの不足**: 現状のオーバーライド機構が一部の主要パラメータ（port, host, enable_tunnel）に限定されており、他の設定項目（解像度、ビットレート、ラジオモード、QRオーバーレイ等）を CLI や一時引数から確実にオーバーライドする一貫した仕組みが不足している。

### 仕様・実装設計
1. **設定優先順位の厳格な階層化 (Configuration Precedence)**:
   - **優先度1 (最高)**: CLI 引数・環境変数・初期化時オーバーライド（明示的に指定された場合のみ、セッション中常に最優先）
   - **優先度2**: `config.json` に保存されたユーザー設定
   - **優先度3 (最低)**: システム既定値（デフォルト値）
2. **オーバーライド値の保護と `config.json` 永続化の分離**:
   - `self._cli_overrides` ディクショナリで CLI / 一時オーバーライド値を独立保持。
   - `get_config(key)` 参照時はオーバーライド値を返しつつ、`save_config()` 実行時は元の永続設定を破損させないクリーンな分離構造を確立。
3. **網羅的な単体テストの整備**:
   - CLI 引数指定時、設定ファイル読み込み時、API からの設定更新時における優先順位と動作を検証する自動テスト（`test_config_overrides.py`）を追加。

### 変更対象予定ファイル
- `streamer_core.py`（設定管理クラス / `_cli_overrides` メカニズムの刷新、`get_config` / `update_config` の整理）
- `gui_streamer.py`（CLI 引数パースと `StreamerCore` へのオーバーライド伝達の統合）
- `tests/test_config_overrides.py`（オーバーライド優先順位と永続化分離の単体テスト）

---

## 8. 🌐 通常ブラウザ利用時のサーバー操作ボタン（再起動・起動）非表示化 【実装完了 ✅】

### 概要
WebリモコンUI（`ui/index.html`）を通常のブラウザ（Chrome / Edge 等）から開いた際、IPC権限を持たず機能しない「再起動」「サーバー起動」ボタンを非表示にし、ローカルアクセス（localhost）での「サーバー終了（停止）」操作は維持するよう表示ロジックを最適化。

### 仕様・実装内容
1. **実行環境判定の整理 (`isIpcAvailable()`)**:
   - `Boolean(window.electron && window.electron.ipcRenderer)` で VRCBeacon（Electron IPC環境）を判定。
2. **通常ブラウザ環境での挙動**:
   - **ヘッダーボタン**:
     - `btnHeaderStop`（サーバー終了）: ローカルホストアクセス時（`isLocal === true`）のみ表示（通常ブラウザでも利用可能）。
     - `btnHeaderRestart`（再起動）: VRCBeacon（IPC環境）かつ `isLocal` の場合のみ表示（通常ブラウザでは非表示）。
     - `btnHeaderLaunch`（起動）: VRCBeacon（IPC環境）かつ `isLocal` の場合のみ表示（通常ブラウザでは非表示）。
   - **オフラインバナー (`offlineBanner`)**:
     - `btnOfflineLaunch`（VRCYouTube を起動する）: VRCBeacon（IPC環境）のみ表示。
     - 通常ブラウザ（localhost）では「ホストPCで VRCYouTubeStreamer.exe を起動してください」という案内と「状態を再確認」ボタンのみを表示。
     - リモート（ゲスト）では「配信サーバーに接続できません / ホストの再開をお待ちください」案内のみを表示。

### 変更対象ファイル
- `ui/index.html`（環境判定ロジックおよびライフサイクルボタンの表示制御）
- `plugin/ui/index.html`（自動同期）

---

## 9. 📻 再生モード3分岐 ＆ 写真・動画キュー完全分離 ＆ スライドショー安定化 (Playback Modes & Photo Pool Separation) 【実装完了 ✅】

### 概要
動画・ラジオ・スライドショーの3大再生モードへの明確な分岐、写真プール（アルバム）と動画キューの完全分離、および写真0枚時のフォールバック案内表記（パターンA）を導入し、スライドショー再生の動作安定化とキュー混在による不具合を根本解決。

### 実装内容
1. **3つの再生モード（`playback_mode`）の明確化**:
   - 🎬 **動画モード (`video`)**: 動画キューを通常再生。**写真は一切混入しない**。
   - 📻 **ラジオモード (`radio`)**: 動画キューの音声のみ抽出＋背景（カード / 写真プール全件スライドショー / 待機画面）を極小帯域（~300kbps）で配信。
   - 🖼️ **スライドショーモード (`slideshow`)**: 写真プール内の写真を指定秒数ごとに自動巡回配信（無音）。
2. **動画キュー (`play_queue`) と 写真プール (`photo_pool`) の完全分離**:
   - アップロードされた写真は写真プールに保持され、動画を再生しても消滅しない。動画キューへの写真混入を完全防止。
3. **写真プール（UI / API）での並び替え・削除機能**:
   - WebリモコンおよびGUI上で写真の「個別削除」「並び替え（前へ/次へ）」「全削除（クリア）」が可能。
4. **写真0枚時のフォールバック案内（パターンA）**:
   - 写真が0枚のときは待機画面に下部案内バー（`📷 スライドショー写真が未登録です（Webリモコンから写真をアップロードできます）`）を Pillow で合成表示。写真が投稿され次第即座にスライドショーへ復帰。
5. **`photo_pool` の完全クリーンアップ（セッション限定・残骸ゼロ）**:
   - ソフト終了時および次回起動時に、`hls_output/images/` 配下の全キャッシュ画像を完全削除。PC内に一時写真が残留しない安全設計。
6. **Web UI / GUI / 単体テストの完備**:
   - Webリモコン（3ボタントグル＋写真プール管理カード）、デスクトップGUI（3モードセグメントボタン）、包括的単体テスト（`test_playback_modes.py` 全6件通過）。

### 変更ファイル
- `streamer_core.py`（`playback_mode` 実装、キューと写真プールの完全分離、写真0枚フォールバック案内バー合成、再生ループ3分岐制御）
- `api_server.py`（`/api/status`, `/api/control`, `/api/upload` の 3モード・写真プールCRUD対応）
- `ui/index.html` / `plugin/ui/index.html`（3ボタントグルUI、写真プール管理カード・操作ロジック追加）
- `gui_streamer.py`（GUIヘッダーに3モードセグメントボタン追加、設定同期）
- `config.dist.json`（`playback_mode: "video"` 追加）
- `test_playback_modes.py`（3モード動作・写真プール分離・案内バー合成の単体テスト）
- `test_radio_unit.py`（写真プール対応への修正）

---

## 10. 📱 待機画面・通常動画・ラジオ全画面でのQRコード表示モード統括・修正 (QR Code Overlay & Standby Modes) 【実装完了 ✅】

### 概要
待機画面（Standby）、通常動画再生時、ラジオモード時のすべてにおいて、Webリクエスト用QRコードおよび接続URLのオーバーレイ表示が意図通りに動作しない、またはFFmpegフィルタエラーで配信が落ちる不具合を解消し、全配信モードでの設定仕様を完全統一。

### 実装内容
1. **待機画面固定画像モード (`standby_mode: "image"`) での QR 合成対応**:
   - `standby_mode == "image"` 時に `overlay_qr_enabled: true` の場合、Pillow (`alpha_composite`) で待機画像（カスタム画像 / デフォルト画像 / フォールバック画面）上にQRオーバーレイを合成して保存するよう修正。
2. **堅牢な FFmpeg フィルタグラフビルダーの導入 (`_build_video_filter_complex`)**:
   - 音声ストリームの有無による入力インデックス（`qr_idx`）や `scale2ref` / `overlay` / `drawtext`（時計）の組み合わせを安全に組み立てる共通ビルダーメソッドを整備。
3. **ラジオモードの QR オーバーレイ対応 (`play_radio`)**:
   - `card` / `standby` 背景使用時、`overlay_qr_enabled` が有効な場合は動画再生時と同様に FFmpeg `-filter_complex` でQRコードを合成して配信。
   - スライドショー（`slideshow`）は `get_image_for_playback()` でPillow合成済みのため、二重合成を自動防止するガードを装備。
4. **単体テスト整備**:
   - `test_standby.py`（待機画面QR合成検証2件）および `test_qr_overlay.py`（ビルダー・QR画像生成検証9件）を追加し、全テストパスを確認。

---

## 11. ⏰ 配信実時刻（LIVE時計）オーバーレイ機能の修正・堅牢化 (Live Clock Overlay & Sync Marker) 【要対応 ⚠️】

### 概要
配信映像（待機画面・通常動画・ラジオ画面）上にリアルタイムの配信時刻（JST）をオーバーレイ表示し、VRChat内プレイヤーとの遅延可視化とリシンク判断を可能にする機能において、FFmpeg の `drawtext` フィルタによるクラッシュやフォント不備を解消し、安全に動作させる修正。

### 現状と原因
1. **無条件適用によるクラッシュ**:
   - `play_radio`、`play_image`、`play_standby_loop` において、`overlay_clock_enabled` の設定状態を確認せず無条件に `-vf drawtext=...` を付与している。
2. **フォントパス / エスケープ不備による FFmpeg エラー**:
   - Windows 環境のフォントパス（`C\:/Windows/Fonts/...`）のコロンやバックスラッシュのエスケープが環境によって FFmpeg に正しく解釈されず、`Font file not found` で配信プロセスが即死する。
3. **FFmpeg の `libfreetype` 依存性**:
   - 使用中の FFmpeg バイナリに `drawtext` フィルタが含まれていない場合、またはフォント取得に失敗した場合のフォールバックがなく配信不能に陥る。

### 仕様・修正設計
1. **設定フラグの厳格な尊重**:
   - `overlay_clock_enabled`（または `overlay_clock_video`）が有効な場合のみ時計オーバーレイを適用し、無効時はフィルタをバイパス。
2. **静止画（PIL合成）と動画（FFmpeg drawtext）の使い分け**:
   - 待機画面・ラジオカード・静止画配信では、FFmpegの `drawtext` ではなく **Pillow (PIL) による画像生成時オーバーレイ** を優先し、FFmpeg依存と負荷を完全排除。
   - 通常動画再生時のみ FFmpeg の `drawtext` フィルタを適用し、フォント解決とエスケープ（`libfreetype` 互換パス形式）を堅牢化。
3. **エラー検出と安全なフォールバック**:
   - FFmpeg 起動時に `drawtext` フィルタでエラーが発生した場合、時計なしの通常パイプラインへ自動フォールバックして配信停止を防止。

### 変更対象予定ファイル
- `streamer_core.py`（`get_live_clock_drawtext_filter`, `generate_standby_image`, `generate_radio_card_image`, 各配信メソッド）
- `gui_streamer.py` / `ui/index.html`（時計オーバーレイ設定UI）
- `tests/test_clock_features.py`


