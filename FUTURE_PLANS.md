# 🔮 将来の機能拡張案・バックログ (Future Ideas & Backlog)

本ドキュメントは、VRC_Media_Streamer のバージョンアップ計画、タスク進捗状況、および将来の設計案を記録するバックログです。

---

## 📋 タスク進捗一覧・ステータス表 (Roadmap & Implementation Status)

| No. | カテゴリ | タスク名 / 機能概要 | バージョン | 状態 |
| :---: | :--- | :--- | :--- | :---: |
| **1** | 📻 ラジオ機能 | **YouTubeサムネイル＆ラジオ番組風カード画面の自動生成** (Radio Card Visualizer) | v2.2.0 | 🟢 **実装完了 ✅** |
| **2** | 🔒 セキュリティ | **Webリモコンのパスワード/PIN認証保護機能** (Password Protection) | v2.3.0 | 🟢 **実装完了 ✅** |
| **3** | 🔀 キュー操作 | **キューの表示専用ソート＆種別絞り込み機能** (Display Sort & Filtering) | v2.3.0 | 🟢 **実装完了 ✅** |
| **4** | 📊 帯域・診断 | **配信ビットレート・遅延・FPSのリアルタイム診断表示** (Diagnostics Dashboard) | v2.4.0 | 🟢 **実装完了 ✅** |
| **5** | 📱 UI/統合 | **スマホ向け写真・スクショ一括アップロード機能** (Batch Photo Upload) | v2.4.0 | 🟢 **実装完了 ✅** |
| **6** | 🖼️ 背景選択 | **BGM/ラジオモード時の背景切り替え機能** (Radio Background Selector) | **v2.7.0(再修正)** | 🟢 **実装完了 ✅** |
| **7** | 🎬 互換性 | **実機検証済み対応動画元・プラットフォームの仕様明記** (Platform Compatibility) | v2.5.0 | 🟢 **実装完了 ✅** |
| **8** | 🧩 プラグイン | **Webリモコン＆VRCBeaconプラグインUIの完全統合＆UI正本配置整理** (Integrated UI) | v2.6.0 | 🟢 **実装完了 ✅** |
| **9** | 📻 モード分離 | **再生モード3分岐 ＆ 写真・動画キュー完全分離 ＆ スライドショー安定化** (Playback Modes) | **v2.7.0** | 🟢 **実装完了 ✅** |
| **10** | 📱 QRオーバーレイ | **待機画面・通常動画・ラジオ全画面でのQRコード表示モード統括・修正** (QR Overlay) | **v2.7.0** | 🟢 **実装完了 ✅** |
| **11** | ⏰ 時計表示 | **配信実時刻（LIVE時計）オーバーレイ機能の修正・堅牢化** (Live Clock Overlay) | **v2.7.0** | 🟢 **実装完了 ✅** |
| **12** | 🏷️ 名称変更 | **アプリの名称変更およびREADME・ウィンドウタイトル・UI表記の刷新** (App Renaming) | **v2.8.0** | 🟢 **実装完了 ✅** |
| **13** | 🎬 動画対応 | **写真に加えてMP4等のローカル動画ファイルアップロード・再生対応** (Local Video Upload) | **v2.8.0** | 🟢 **実装完了 ✅** |
| **14** | 📡 配信経路 | **配信先（HLS/TopazChat/汎用RTMP）の選択制対応** (Selectable Streaming Destination) | **v2.9.0** | 🟡 **実装完了・実機検証待ち 🔬** |
| **15** | 🔄 外部依存 | **外部ソース（yt-dlp等）の自動更新・メンテナンス機能** (External Tools Auto-Update) | 未定 | 🔵 **検討中 📋** |
| **16** | 🎨 GUI刷新 | **ホストソフトGUIのモダン化・リデザイン** (Host GUI Modernization) | 未定 | 🔵 **検討中 📋** |
| **17** | 🎵 ラジオ | **ラジオモード時のクロスフェード・滑らか切り替え** (Smooth Crossfade) | 未定 | ⚪ **実装予定 📝** |
| **18** | ⚡ 性能 | **FFmpeg ハードウェアエンコード（NVENC / QSV / AMF）対応** (HW Encoding) | 未定 | ⚪ **実装予定 📝** |
| **19** | 🛠️ CLI | **CLI 引数・環境設定オーバーライド機構の総点検・堅牢化** (CLI Overrides Overhaul) | 未定 | ⚪ **実装予定 📝** |
| **20** | 🌐 UI/権限 | **通常ブラウザ利用時のサーバー操作ボタン（再起動・起動）非表示化** (Button Visibility) | v2.6.0 | 🟢 **実装完了 ✅** |

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

## 11. ⏰ 配信実時刻（LIVE時計）オーバーレイ機能の修正・堅牢化 (Live Clock Overlay & Sync Marker) 【実装完了 ✅】

### 概要
配信映像（通常動画・ラジオ画面・静止画/スライドショー・待機画面）において、配信実時刻（JST）をオーバーレイ表示し、VRChat内プレイヤーとの遅延可視化とリシンク判断を可能にする機能において、設定フラグを厳格に尊重するパイプライン制御を実装し、無効時の不要なフィルタ負荷やフォント起因のFFmpegエラーを解消。

### 実装内容
1. **設定フラグ（`overlay_clock_enabled` / `overlay_clock_video`）の厳格な尊重**:
   - `play_radio`、`play_image`、`play_standby_loop` において、設定が無効な場合は FFmpeg に一切の `-vf`（`drawtext`）を付与せずバイパス。
   - 設定が有効な場合のみ、リアルタイム時刻を描画する `drawtext` フィルタを適用。
2. **位置設定共通ヘルパーの導入 (`get_clock_filter_for_config`)**:
   - `overlay_clock_position`（`top-right`, `top-left`, `bottom-right`, `bottom-left`）に応じた座標計算と `drawtext` 文字列生成を共通関数化し、全配信パイプラインで一元管理。
3. **フォントパス解決とエスケープの堅牢化 (`get_drawtext_font_path`)**:
   - Windows・Linux・macOSのフォント探索候補を拡充し、パス区切り文字およびコロンのエスケープ（`C\:/...`）を安全に処理。
4. **包括的な単体テスト整備**:
   - `test_clock_features.py` に時計フィルタヘルパー、位置座標計算、`-filter_complex` ビルダー組み合わせ、および各配信パイプラインでのフラグチェック検証（計8項目）を追加し、全テストパスを確認。

### 変更ファイル
- `streamer_core.py`（`get_clock_filter_for_config`, `get_drawtext_font_path`, `play_radio`, `play_image`, `play_standby_loop`, `play_video`）
- `test_clock_features.py`（位置座標・ビルダー組み合わせ・パイプラインフラグ検証テスト拡充）
- `FUTURE_PLANS.md`（タスク11完了記録）

### 🐛 実機NG → 原因特定・修正（2026-08-27）

**症状**: 全モードで時計がまったく表示されない（配信は正常、単体テスト8件は全通過）。

**根本原因**: `drawtext` の text に書いていた時刻書式のコロンのエスケープが、
フィルタグラフ解析の段階で外れてしまうこと。

- 生成していた文字列: `text='● LIVE %{localtime\:%H\:%M\:%S} JST'`
- FFmpeg がフィルタ記述をアンエスケープするため、drawtext の展開器には
  `%{localtime:%H:%M:%S}` として渡り、コロンが引数区切りと解釈されて4引数になる。
- 結果 `[Parsed_drawtext_0] %{localtime} requires at most 1 arguments` が出て
  **text全体が空になり、何も描画されない**。
- **FFmpegの終了コードは 0 のまま**（＝配信は落ちないので気づきにくい）。

**修正**: 時刻書式に生のコロンを書かず、strftime の `%T`（＝`%H:%M:%S`）を使用。
`text='● LIVE %{localtime\:%T} JST'` に変更（[streamer_core.py:169](streamer_core.py)）。

**検証**: 実際に FFmpeg を起動して1フレーム描画し、4方向の表示位置すべてで
`● LIVE HH:MM:SS JST` が描画されること、QRオーバーレイ併用（`-filter_complex`）でも
描画されることを確認済み。

**テストの盲点と対策**: 既存テストはコマンド文字列に `drawtext=` が含まれるかを見るだけで、
FFmpegを一度も起動していなかったため素通りしていた。
`test_clock_features.py` に **実際にFFmpegを起動して描画結果を検証する回帰テスト**
（`test_drawtext_filter_actually_renders`）を追加。旧文字列ではこのテストが落ちることを確認済み。

**残作業**: VRChat実機での最終確認（表示位置・視認性・遅延把握の実用性）。

---

## 12. 🏷️ アプリの名称変更およびREADME・ウィンドウタイトル・UI表記の刷新 (App Renaming & Rebranding) 【実装完了 ✅】

### 概要
アプリケーションの正式名称変更に伴い、ドキュメント（`README.md`、`README.txt`）、デスクトップGUIウィンドウタイトル（`gui_streamer.py`）、WebリモコンUIタイトル（`ui/index.html`）、ビルド設定、バッチファイル、プラグイン等の各所に存在する旧アプリ名の表記を一括で更新・統一するタスク。

### 検討・改訂対象箇所
1. **ドキュメント類の改訂**:
   - `README.md` / `README.txt`: アプリ名、概要説明、起動手順、各種設定ファイルの説明を新名称に更新。
   - `HANDOVER_*.md` / ドキュメント内の名称リンクやタイトルの整理。
2. **GUI / Web UI の表示刷新**:
   - `gui_streamer.py`: ウィンドウタイトル（`self.title("...")`）、ヘッダーラベル（`title_label`）、各種ダイアログのタイトル表記。
   - `ui/index.html` / `plugin/ui/index.html`: ブラウザタブタイトル（`<title>`）、Webリモコンヘッダーロゴ・名称。
   - `api_server.py`: UIアセット未検出フォールバック画面のタイトル・メッセージ。
3. **ビルドおよび起動スクリプト**:
   - `build_exe.py` / `VRC_Media_Streamer.spec`: 出力EXE名、ZIPアーカイブ名、バッチファイル内の文言および起動コマンド。
   - `Start_Normal.bat` / `Start_LocalTest.bat`: 表示ログや起動メッセージ。
4. **プラグイン・連携部分**:
   - `vrcbeacon-plugin` 側のマニフェスト、UI、表示名の整合性確保。

### 変更対象予定ファイル
- `README.md` / `README.txt`
- `gui_streamer.py`
- `ui/index.html` / `plugin/ui/index.html`
- `api_server.py`
- `build_exe.py` / `VRC_Media_Streamer.spec`
- `Start_Normal.bat` / `Start_LocalTest.bat`
- `FUTURE_PLANS.md`

---

## 13. 🎬 写真に加えてMP4等のローカル動画ファイルアップロード・再生対応 (Local Video File Upload & Playback) 【実装完了 ✅】

### 概要
Webリモコン（スマホブラウザ / PC）およびホストPCのデスクトップGUIから、画像（写真・スクショ）だけでなく **MP4 / MOV / WebM などのローカル動画ファイル** を直接アップロード（またはドラッグ＆ドロップ）し、動画キュー（`play_queue`）に追加してVRChat向けにHLS配信できる機能。

### 背景と利点
- **現状**: 動画再生はYouTube等のオンラインURL（`yt-dlp` 解析）が前提であり、ローカルメディアは写真プール（静止画）のみの対応となっている。
- **利点**:
  - スマホで撮影した動画やPC内の録画ファイルをYouTubeにアップロードすることなく、即座にVRChatワールド内の大画面・プレイヤーで皆と共有・鑑賞可能。
  - ローカルファイルのため `yt-dlp` による抽出処理が不要で、キュー追加から再生開始までのラグが極小。

### 仕様・実装設計
1. **アップロードAPIの動画対応拡張 (`/api/upload`)**:
   - MIMEタイプ（`video/mp4`, `video/quicktime`, `video/webm`, `video/x-matroska` 等）および拡張子による動画判別。
   - **アップロード上限・チャンク対応**:
     - 静止画上限（20MB）と分離し、ローカル動画用の上限（例: 100MB〜500MB、設定可能）を設定。
   - **保存場所とサニタイズ**:
     - `hls_output/videos/`（または一時メディアディレクトリ）にUUIDベースの安全なファイル名で保存。
     - セッション終了時または再生完了時に一時動画を自動クリーンアップする安全設計。
2. **キュー統合と再生パイプライン (`StreamerCore`)**:
   - キューアイテムの種別として `type: "local_video"` を追加（`title`, `url` に代わり `file_path`, `duration` を保持）。
   - `play_video` / `play_radio` 実行時、URL抽出を行わずローカルファイルパスを直接 FFmpeg の入力（`-i <path>`）として渡すことで即時トランスコード配信。
3. **UI / 操作性の拡張**:
   - **Webリモコン (`ui/index.html`)**:
     - メディア投稿エリアに「動画を追加（MP4/MOV）」オプションを追加（または写真/動画の自動判別）。
     - 動画アップロード進捗バー（ProgressBar）を表示。
   - **ホストGUI (`gui_streamer.py`)**:
     - 「動画ファイルを追加」ボタンおよびウィンドウへの動画ドラッグ＆ドロップ対応。
4. **セキュリティ・負荷対策**:
   - ゲストからの動画アップロードに対する容量制限・レートリミットおよびパスワード認証の徹底。

### 変更対象予定ファイル
- `streamer_core.py`（ローカル動画アイテムのキュー処理、FFmpeg入力パイプライン、動画削除クリーンアップ）
- `api_server.py`（動画アップロード受付、MIME/サイズ判定、レートリミット分離）
- `ui/index.html` / `plugin/ui/index.html`（動画アップロードUI、プログレスバー、キュー表示）
- `gui_streamer.py`（ローカル動画選択ダイアログ、D&D対応）
- `config.dist.json`（動画アップロードサイズ上限等の設定項目）
- `tests/test_local_video.py`（ローカル動画アップロード・キュー・再生単体テスト）

---

## 14. 📡 配信先（HLS / TopazChat / 汎用RTMP）の選択制対応 (Selectable Streaming Destination) 【実装完了・実機検証待ち 🔬】

### 概要
現在ハードコードされている配信経路「ローカルHLS生成 → Flask配信 → Cloudflare Quick Tunnel（`*.trycloudflare.com`）」を抽象化し、**配信先（destination）を設定で切り替えられる**ようにする。特に VRChat 向けに設計された **TopazChat（RTMP入力 → `rtsp://` 出力）** を第一候補として追加する。

### 背景と目的
- **現状の課題（ToS）**: 動画実体そのものを Cloudflare Quick Tunnel 経由で流しており、Cloudflare の非HTMLコンテンツ制限（ToS 2.8）に対してグレーな利用形態。Quick Tunnel も本来は開発用途で、恒常運用を前提としていない。
- **現状の課題（遅延）**: `hls_segment_time: 3` × プレイヤー側バッファ約3セグメントで、VRChat 側の実効遅延は **約9〜12秒**。ワールドで複数人が同時視聴する用途では反応のズレが大きい。
- **狙い**: 映像を TopazChat 等へ逃がすことで、
  1. 遅延を **1秒未満〜2秒** に短縮、
  2. Cloudflare トンネルの役割を **Webリモコンの HTML / JSON（制御系）のみ** に縮小し、ToS上のグレーさを実質解消する。

### 方針（重要な設計判断）
本タスクは「3つの配信先を同列に並べる」ものではない。優先度と扱いを明確に分ける。

| 配信先 | 位置付け | VRChat側遅延 | 備考 |
| :--- | :--- | :---: | :--- |
| **`hls`（現行）** | **既定値・フォールバック** | 約9〜12秒 | Cloudflare Quick Tunnel 経由（トンネル無効時のみローカル完結）。他経路の失敗時の退避先として必ず残す |
| **`topaz`（TopazChat）** | **本命・最優先実装** | 1秒未満〜2秒 | VRChat向け設計。AVProで `rtspt://topaz.chat/live/<KEY>` を直接再生。映像2Mbps / 音声320kbps の上限あり |
| **`generic_rtmp`** | 上級者向けオプトイン | 任意 | 自前 nginx-rtmp / MediaMTX 等。URL＋キーを手入力 |

- **YouTube Live は推奨destinationとして提供しない。** 理由:
  1. 本アプリは `yt-dlp` で取得した他者の YouTube 動画を再生する設計であり、それを自チャンネルへ再送出すると Content ID・著作権警告の直撃対象となる。リスクの質が「トンネルが止まる」から **「ユーザー本人の Google アカウント / チャンネルが停止」** に悪化する。
  2. 遅延が15〜30秒とHLS直より更に悪化し、視聴側でも `yt-dlp` 解決を要するため依存が増える。
  3. **QRオーバーレイ（タスク10）との相性が致命的** — Webリモコンのトンネル URL を画面に焼いているため、公開ライブへ流すとリモコンURLが全世界へ露出し、PIN認証（タスク2）だけが最後の防壁になる。
  - どうしても使う場合は `generic_rtmp` の枠内で、UI上に明示的な自己責任警告を出したうえで利用者が自分でURLを入力する形に留める。

### TopazChat の公式仕様・規約上の制約（2026-08-28 公式README確認）

出典: [TopazChat/TopazChat (GitHub)](https://github.com/TopazChat/TopazChat)

| 項目 | 内容 | ソフト側の対応 |
| :--- | :--- | :--- |
| RTMP投稿先 | `rtmp://topaz.chat/live` | **ハードコードせず `config.dist.json` に置く**（個人運営のためホスト変更・終了があり得る。タスク15と同じ思想でリビルド不要に） |
| RTSP再生URL | `rtspt://topaz.chat/live/<StreamKey>`（TCP強制版を既定とする） | ワールド貼付用URLとして生成・表示 |
| 映像上限 | **2Mbps**（推奨1500kbps） | **ソフト側のハードリミットとして実装。設定で上限超過を許可しない** |
| 音声上限 | **AAC 320kbps ステレオ**（推奨192kbps） | 同上。既定は推奨値 |
| 超過時の挙動 | 「大きく上回ると配信が強制的に切断されます」 | 上限を超える設定値は保存時点で拒否 or クランプ |
| 利用条件 | **個人利用は無償。法人が運営主体のイベント・番組制作等の法人利用は有償（要問い合わせ）** | **UIに「法人利用の場合は別途TopazChatへ問い合わせが必要」の注記を表示**。本ソフトは配布物であり、黙って法人利用を可能にすると規約違反を助長するため |
| 運営形態 | 個人運営・無償提供（サーバ費は開発者負担、PixivFANBOXでカンパ募集） | **UIにFANBOX / 公式サイトへのリンクを設置**。既定destinationは `hls` のままとし、TopazChatは明示的に選ばせる（配布ソフトが全ユーザーの帯域を無断で他者の善意サーバへ向けない） |
| サードパーティツール | 公式READMEに可否の記載なし（OBSの手順のみ記載。禁止規定も明示的許可もなし） | 禁止されていないため実装可。ただし **公式を騙らない**: ロゴ・ブランド素材は使用せずテキスト名のみ、「本ソフトはTopazChatの公式ツールではありません」を明記 |
| 再接続 | 記載なし | **指数バックオフ**で実装。無限リトライで相手サーバを叩かない |

### 仕様・実装設計
1. **シンク（出口）の抽象化**:
   - 現状、配信先を定義しているのは `streamer_core.py` の `ensure_hls_receiver()` **ただ1箇所**。永続FFmpegが `pipe:0` から MPEG-TS を読み、各再生アイテムのFFmpegが `current_stdin` へ流し込む構造のため、**シンクだけを差し替えれば destination 化できる**（継ぎ目が1関数に閉じている）。
   - `ensure_hls_receiver()` → `ensure_stream_sink()` へ改称し、`config["output_mode"]`（`"hls"` / `"topaz"` / `"generic_rtmp"`）で出力引数を分岐させる。
2. **コーデック方針（TopazChat経路では再エンコード必須／確定）**:
   - 現行シンクは `-c:v copy -c:a copy`。HLS はセグメント境界の不連続に寛容だが、**RTMP は再生アイテム切替時のタイムスタンプ跳躍・解像度/パラメータ変化でサーバ側から切断されやすい**。
   - さらに TopazChat には **映像2Mbps / 音声320kbps の明確な上限があり、超過すると強制切断される**（上記「公式仕様・規約上の制約」参照）。元動画のビットレートが上限を超えていれば接続した瞬間に切られるため、**`-c copy` の素通しは成立しない**。
   - → **RTMP系destinationではシンク側での再エンコードを必須とする**（`-c:v libx264 -b:v <上限内> -maxrate -bufsize -g <固定GOP> -keyint_min <同値> -c:a aac -b:a <上限内>`）。これは推測ではなく公式仕様から導かれる確定事項であり、**実測が必要なのはCPUコストの方のみ**（タスク18のハードウェアエンコード対応と併せて検討）。
3. **destination別プロファイルの分離**:
   - `hls_segment_time` / `hls_list_size` は RTMP では意味を持たない。設定を destination ごとのプロファイルに分離し、RTMP側は ビットレート / GOP長 / 再接続リトライ間隔 を持つ。
4. **フォールバック設計（fail-safe）**:
   - TopazChat は有志運営の無料サービスであり、可用性の保証がない。**接続失敗・切断検知時に自動で `hls` へフォールバック**し、配信自体は途切れさせない。
   - RTMP 切断・再接続ループは、ローカルHLSには存在しなかった **新規の障害モード** として明示的にハンドリングする。
5. **ストリームキーの機密扱い・自動生成**:
   - `config.json` は `.gitignore` 済み（`.gitignore:47`）のためリポジトリ流出の心配はないが、**`/api/status` レスポンス・`log_print` のログ出力・GUI表示・QRコードの全経路でマスク必須**。
   - **TopazChat のストリームキーは任意文字列で、公式に決め方の記載がない。** 同じキーで誰でも RTMP 投稿できるため、`test` のような短いキーだと **第三者に配信を乗っ取られる**。初回設定時に **長いランダム文字列（32文字以上）をソフト側で自動生成**し、手入力は上書き可能なオプションとする。
6. **URL概念の分離**:
   - `get_status()` が返す `tunnel_url` / `public_url`（`streamer_core.py:543` 付近）は現在「動画URL」と「リモコンURL」を兼ねている。destination 導入後は両者が別物になるため、**「ワールドの動画プレイヤーに貼るURL」と「Webリモコンを開くURL」を別フィールドとして明確に分離**する。QRオーバーレイが焼くのは後者のみ。
   - Cloudflare トンネル自体は **Webリモコンのために引き続き必要**であり、全廃はしない。

### 実装フェーズ
- **Phase 1**: `output_mode: "hls" | "topaz"` の2択のみ実装。TopazChatキー入力UI＋失敗時のHLS自動フォールバックまで。これで遅延とToSの両課題が解決する。
- **Phase 2**: `generic_rtmp`（RTMP URL＋ストリームキー手入力）を上級者向けに追加。自己責任警告表示を伴う。

### 事前確認が必要な事項（設計前に実測すること）
- **CPUコストの実測**: シンク側再エンコード（`libx264` 2Mbps上限）を常時走らせた場合のホストPC負荷。ラジオモードの超低負荷設計（200kbps / 2fps 静止画）との共存可否を含めて計測する。→ 負荷が問題になる場合はタスク18（NVENC / QSV / AMF）の前倒しを検討。
- **アイテム切替時のRTMP接続維持**: 再生アイテム切替（解像度・フレームレート変化）をまたいで RTMP セッションが維持できるか。維持できない場合は、シンク側で解像度・fps を固定（`scale` + `fps` フィルタ）してパラメータ変化そのものを消す。
- **VRChat側の再生可否**: `rtspt://` を再生できるのは AVPro プレイヤーのみ（Unity Video Player 不可）である点の、対象ワールドでの成立確認。

### 変更対象予定ファイル
- `streamer_core.py`（`ensure_hls_receiver()` のシンク抽象化、destination分岐、再接続・フォールバック、`get_status()` のURL分離）
- `api_server.py`（`/api/status` でのストリームキーのマスク、destination切替API）
- `ui/index.html` / `plugin/ui/index.html`（配信先選択UI、キー入力欄のマスク表示、現在の配信先表示）
- `gui_streamer.py`（配信先選択・キー入力の設定画面、接続状態表示）
- `config.dist.json`（`output_mode`、TopazChatのRTMP/RTSPエンドポイント（ハードコード禁止）、destination別プロファイル、ビットレート上限、キー項目の追加）
- `tests/test_destination.py`（destination切替・フォールバック・キーマスクの単体テスト）

### 依存・前提
- タスク11（LIVE時計オーバーレイ）の実機確認は **2026-08-28 完了**。本タスクの着手ブロッカーは解消済み。
- タスク18（ハードウェアエンコード対応）と設計上の関連あり（RTMP再エンコードが必要となった場合、NVENC等の適用でCPUコストを相殺できる可能性）。

### 実装記録（2026-08-28 / ブランチ `feature/task14-stream-destination`）

Phase 1（`hls` / `topaz`）と Phase 2（`generic_rtmp`）を同時に実装した。
シンクの分岐は1箇所に閉じており、`generic_rtmp` は同じRTMP経路の宛先違いに過ぎないため、
分割するより一度に入れた方が差分が小さく済むと判断した。

- `ensure_hls_receiver()` → **`ensure_stream_sink()`** へ改称し、`build_sink_command(mode)` で
  出口だけを差し替える構造にした。旧名は別名として残してある（プラグイン・既存テスト互換）。
- RTMP系は設計どおり**再エンコード必須**（`scale`+`pad`+`fps` 固定 → `libx264` / `aac`、
  GOP = `fps × rtmp_gop_seconds`）。TopazChat の 2Mbps / 320kbps は保存時クランプで担保。
- ストリームキーは `secrets.token_urlsafe(30)`（40文字）で自動生成。`/api/status`・
  `/api/config`・POSTボディのログの全経路でマスクし、生キーは localhost 限定の
  `/api/destination`（`reveal_key`）でのみ取得できる。
- `get_status_data()` に `video_url`（ワールドに貼る）と `remote_url`（Webリモコン）を分離して追加。
  QRが焼くのは従来どおり後者のみで、この点は変更していない。

#### ★実測でひっくり返った設計前提（2026-08-28）

当初は「RTMPシンクは接続失敗時に即座に終了するので、起動直後の生存確認で失敗を検知できる」
という前提で組んだが、**誰も listen していないポートを宛先にしても FFmpeg は2秒間平然と生きていた**。
原因は入力が `pipe:0` であること — 入力データが流れ始めてストリーム情報が確定するまで、
FFmpeg は出力側のRTMPハンドシェイクを開始しない。つまり起動直後の生存は接続成功を意味しない。

対策として **投稿先へのTCP到達性を起動前に確認**（`probe_rtmp_endpoint()`）する方式へ変更した。
併せて、失敗計数を呼び出しをまたいで持ち越すようにした（毎回リセットすると
「起動しては数秒で切断」を繰り返す相手に対して永遠に再接続し、退避条件へ到達できない）。
回帰防止として `test_destination.py` に「到達できない宛先にFFmpegを起動しないこと」を追加済み。

#### 未検証（実機確認が必要）

- **実際のTopazChatへの投稿**（到達可能なRTMPサーバーが手元に無いため、成功パスは未検証）
- **再エンコードのCPUコスト**（`libx264` 常時稼働。ラジオモードとの共存可否を含む）
- **アイテム切替をまたぐRTMPセッション維持**（解像度・fps固定で消しにいく設計だが未実測）
- **VRChat（AVPro）での `rtspt://` 再生可否**

---

## 15. 🔄 外部ソース（yt-dlp等）の自動更新・メンテナンス機能 (External Tools Auto-Update & Maintenance) 【検討中 📋】

### 概要
YouTube側のプレイヤー仕様変更や暗号化シグネチャ変更（n-sig/JSチャレンジ/PO-Token等）に伴い、動画・音楽の解析・抽出ができなくなる問題を防止するため、`yt-dlp` 等の外部依存バイナリをアプリ本体の再インストールなしで自動的またはワンクリックで最新版へ更新できる機能。

### 背景と課題
- **現状**: `yt_dlp` は PyInstaller によって `VRC_Media_Streamer.exe` の内部に静的バンドルされている。
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
   - `VRC_Media_Streamer 本体`: GitHub Releases API を照会し、「最新バージョン vX.X.X が公開されています」の通知のみ表示。

### 変更対象予定ファイル
- `streamer_core.py`（外部 `yt-dlp.exe` 呼び出し、JSONパース、`-U` 実行/更新マネージャー、エラー時のリカバリ処理）
- `api_server.py`（`/api/system/update_ytdlp` エンドポイント、バージョン情報の返却）
- `build_exe.py`（`yt-dlp.exe` の配布パッケージ同梱処理、PyInstaller からのモジュール除外最適化）
- `config.dist.json`（`auto_update_ytdlp: true` 設定項目の追加）
- `gui_streamer.py`（設定タブに yt-dlp バージョン表示＆「今すぐ更新」ボタン追加）
- `ui/index.html`（Webリモコン設定モーダルに更新ボタン＆バージョン表示追加）
- `README.md` / `README.txt`（構成ファイルの説明に `yt-dlp.exe` を追加）

---

## 16. 🎨 ホストソフトGUIのモダン化・リデザイン (Host Software GUI Modernization) 【検討中 📋】

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

## 17. 🎵 ラジオモード時のクロスフェード・滑らか切り替え (Smooth Crossfade in Radio Mode) 【実装予定 📝】

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

## 18. ⚡ FFmpeg ハードウェアエンコード（NVENC / QSV / AMF）対応 (Hardware-Accelerated Video Encoding) 【実装予定 📝】

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

## 19. 🛠️ CLI 引数・環境設定オーバーライド機構の総点検・堅牢化 (CLI Arguments & Config Overrides Overhaul) 【実装予定 📝】

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

## 20. 🌐 通常ブラウザ利用時のサーバー操作ボタン（再起動・起動）非表示化 【実装完了 ✅】

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
     - `btnOfflineLaunch`（VRC_Media_Streamer を起動する）: VRCBeacon（IPC環境）のみ表示。
     - 通常ブラウザ（localhost）では「ホストPCで VRC_Media_Streamer.exe を起動してください」という案内と「状態を再確認」ボタンのみを表示。
     - リモート（ゲスト）では「配信サーバーに接続できません / ホストの再開をお待ちください」案内のみを表示。

### 変更対象ファイル
- `ui/index.html`（環境判定ロジックおよびライフサイクルボタンの表示制御）
- `plugin/ui/index.html`（自動同期）
