# VRCYouTube Streamer

YouTubeの動画・プレイリストをHLSストリーム（`.m3u8`）に変換し、Cloudflare Tunnel経由でVRChatワールド内動画プレイヤー（iwaSync3, YPlay, ProTV等）やブラウザから再生できるようにするストリーミングサーバーです。

GUI画面からの直感的な操作に加え、**外部アプリ（VRCBeacon等）から遠隔操作できるHTTP APIサーバー（ヘッドレスモード）**を備えています。

---

## 🌟 主な機能

1. **デュアル動作モード**:
   * **GUIモード**: CustomTkinter製のダークテーマUIで手動操作
   * **ヘッドレス / APIサーバーモード**: GUIを表示せず、軽量バックグラウンドサーバーとして動作
2. **動画＆写真共有・スライドショー機能**:
   * **YouTube動画＆プレイリスト再生**: `yt-dlp` + `ffmpeg` による高画質・安定ストリーミング
   * **📻 BGM / ラジオモード (帯域・バッファ極小化 & サムネイルカード自動生成)**:
     - YouTube動画から高音質音声ストリーム（`bestaudio`）のみを抽出し、自動生成された「1920x1080 サムネイル＆楽曲情報カード画面」（または待機画面/写真スライドショー）と合成して超低帯域（約250〜350kbps、通常動画比90%以上削減）でHLS配信。
     - VRChatでのバッファ詰まりや多人数インスタンスでの遅延を極小化。波形イコライザーやQRコード、シークバー等の不要な要素を省いたシンプルで洗練されたアルバムアート画面を自動生成。
   * **写真・画像の一括共有 (Multi-photo upload)**: スマホやPCから複数枚の画像（JPEG, PNG, WebP等）をまとめて選択・キューへ一括追加可能
   * **スライドショー操作 (GUI / Web)**: 表示秒数切り替え（5s〜120s）や自動送りON/OFF（一時停止/再開）をGUI下部バーおよびWebリモコンからリアルタイム操作可能
3. **RESTful HTTP JSON API (CORS対応)**:
   * 外部アプリ（Vue 3, Electron, Node.js, Python等）からHTTPリクエスト経由で状態監視・キュー追加・再生制御・終了が可能
4. **リッチなキュー操作**:
   * **ドラッグ＆ドロップ並び替え**（オートスクロール対応）＋ **「▲」「▼」ボタン**の両立
   * **即時シャッフル (Shuffle List)** & **シャッフル再生モード (Shuffle Play)**
   * **キュー保持ループ再生モード (Loop Queue)**: 再生終了動画・写真を自動でキュー末尾に戻しエンドレス再生（※単方向キュー設計のため不要なPrevボタンは廃止）
5. **QRコード・URL上書き表示 (QR Overlay)**:
   * 配信映像上および待機画面に、Webリクエスト用のQRコードと手入力用URLをウォーターマークとして上書き表示可能。
   * **コンパクトモード（右下小さく）** と **フル画面モード（中央大画面）** を選択可能。
   * ※注意: 動画再生時のQRオーバーレイ有効化時は、FFmpegによるリアルタイム再エンコード処理が行われるためバッファ（読み込み待ち）が発生しやすくなります。
6. **設定管理 (Settings UI & `config.json`)**:
   * サーバーポート、HLSセグメント/バッファ秒数、動画切り替え待機秒数、Webリモコン権限などをGUIおよびAPIから変更・保存可能
7. **Web Player内蔵 & Webリモコン (v2.6.0でプラグインUIと統合)**:
   * ブラウザから `http://localhost:<port>/` にアクセスするだけで、hls.js を利用したインラインHLSプレビュー（折りたたみ可）、キューのリアルタイム操作、スマホからの遠隔動画・写真追加が可能
   * QRコード表示とストリームURLのワンクリックコピーを備え、スマホ縦画面にも対応したレスポンシブUI
   * UIの正本は `ui/index.html` の1ファイルのみ。EXEに同梱され、VRCBeaconプラグインへも同じものが配布されます
   * UIを差し替えたい場合は `VRCYouTubeStreamer.exe` と同じフォルダに `ui\index.html` を置くと、そちらが優先されます
8. **アクセス制御**:
   * 停止・全消去・設定変更などの管理操作は既定でホストPC本人（ループバック）のみ。同一LANの端末は `allow_web_*` の範囲で操作できる「ゲスト」として扱われます
   * 同一LANをホストと同等に信頼する場合のみ `config.json` に `"trust_lan_clients": true` を明示指定してください

---

## 🚀 起動方法

### 1. GUIモードで起動
```bash
python gui_streamer.py
# または配布EXE:
VRCYouTubeStreamer.exe
```

### 2. ヘッドレス / APIサーバーモードで起動
```bash
python gui_streamer.py --headless --port 8080
# または配布EXE:
VRCYouTubeStreamer.exe --headless --port 8080
```

#### コマンドライン引数一覧
| 引数 | 説明 | デフォルト値 |
| :--- | :--- | :--- |
| `--headless` / `-hl` | GUIを起動せずバックグラウンドAPIサーバーとして動作 | なし (GUI起動) |
| `--no-tunnel` / `-nt` | Cloudflareトンネルを起動せずローカルテストモードで動作 | なし (トンネル起動) |
| `--tunnel` | Cloudflareトンネルを明示的に有効化 | 有効 (デフォルト) |
| `--port` / `-p` | APIサーバーおよびHLS配信サーバーのポート番号 | `8000` (または `config.json`) |
| `--host` | サーバーのホストアドレス | `127.0.0.1` |

---

## 📡 HTTP API エンドポイント仕様 (JSON / CORS対応)

すべてのエンドポイントで `Access-Control-Allow-Origin: *` が有効です。

### 1. ストリーマー状態取得
* **Method**: `GET`
* **Path**: `/api/status`
* **Response**:
```json
{
  "status": "streaming",
  "status_detail": "Active (Streaming)",
  "tunnel_url": "https://xxxx.trycloudflare.com",
  "stream_url": "https://xxxx.trycloudflare.com/stream.m3u8",
  "current_video": {
    "title": "Rick Astley - Never Gonna Give You Up",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "duration": 213
  },
  "queue": [
    {
      "title": "Next Video Title",
      "url": "https://www.youtube.com/watch?v=...",
      "duration": 180
    }
  ],
  "loop_queue": true,
  "shuffle": false,
  "is_image": false,
  "image_paused": false,
  "image_display_duration": 15,
  "image_auto_advance": false,
  "overlay_qr_enabled": false,
  "overlay_qr_mode": "bottom-right",
  "permissions": {
    "allow_web_queue_add": true,
    "allow_web_queue_edit": true,
    "allow_web_playback_control": true
  }
}
```
*(※ `status`: `"offline"` / `"buffering"` / `"streaming"` / `"finishing"` / `"error"`)*

---

### 2. キュー追加 (URL)
* **Method**: `POST`
* **Path**: `/api/queue`
* **Body**:
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

---

### 3. 写真・画像アップロード (単一・複数対応)
* **Method**: `POST`
* **Path**: `/api/upload`
* **Content-Type**: `multipart/form-data` または `image/*`
* **Body**: 画像バイナリ（単一ファイル、または `files[]` による複数ファイル一括送信、最大20MB/ファイル）
* **Response**:
```json
{
  "success": true,
  "count": 3,
  "items": [
    {"title": "photo_1.jpg", "url": "local-image://..."},
    {"title": "photo_2.png", "url": "local-image://..."},
    {"title": "photo_3.webp", "url": "local-image://..."}
  ],
  "queue_length": 5
}
```

---

### 4. 再生・キュー制御
* **Method**: `POST`
* **Path**: `/api/control`
* **Body アクション一覧**:
  * **スキップ (次へ)**: `{"action": "skip"}`
  * **📻 BGM/ラジオモードON/OFF**: `{"action": "set_radio_mode", "enabled": true}`
  * **📻 ラジオ背景ソース切替**: `{"action": "set_radio_bg_source", "source": "card"}` *(card / standby / slideshow)*
  * **写真スライドショー一時停止 / 再開トグル**: `{"action": "toggle_image_pause"}`
  * **写真表示秒数変更**: `{"action": "set_image_duration", "duration": 15}` *(5〜120秒)*
  * **写真自動送りON/OFF**: `{"action": "set_image_auto_advance", "enabled": true}`
  * **キュー全消去**: `{"action": "clear_queue"}`
  * **停止＆キュー消去**: `{"action": "stop"}`
  * **キュー即時シャッフル**: `{"action": "shuffle"}`
  * **ループ再生のON/OFF**: `{"action": "set_loop", "enabled": true}`
  * **シャッフル再生のON/OFF**: `{"action": "set_shuffle", "enabled": true}`
  * **指定インデックスの動画/写真削除**: `{"action": "delete_item", "index": 0}`
  * **動画/写真の並べ替え**: `{"action": "move_item", "from_index": 0, "to_index": 2}`

---

### 5. 接続用 QR コード画像取得
* **Method**: `GET`
* **Path**: `/api/qrcode`
* **Response**: PNG 画像ストリーム

---

### 6. サーバー終了
* **Method**: `POST`
* **Path**: `/api/shutdown`

---

### 7. 設定の取得・更新
* **GET `/api/config`**: 現在の設定JSONを取得
* **POST `/api/config`**: 設定JSONを更新して保存（`config.json` に永続化）

---

## ⚠️ トラブルシューティング & よくある質問

### 1. トンネルURLが生成されない / 「Tunnel failed to connect」になる
* **原因: Cloudflare Quick Tunnel の一時的な IP レート制限 (Error 1015 / HTTP 429)**
  * 短時間にアプリの起動・再起動を連続して繰り返した場合、Cloudflare 側の無料 Quick Tunnel API（`trycloudflare.com`）によって接続元 IP アドレスに一時的な接続制限（クールダウン）がかけられることがあります。
* **対処法**:
  1. **数分〜10分程度待機する（推奨）**: プロセスを停止した状態で数分待つと、Cloudflare 側のレート制限が自動的に解除され、再び URL が発行されるようになります。
  2. **回線 IP を変更する**: お急ぎの場合は、ルーターの再起動やスマホのテザリング回線に一時切り替えることで即座に再接続が可能です。
  3. **ローカル環境でのテスト**: 同一 PC または同一 Wi-Fi 内での再生テストであれば、トンネル URL ではなく `http://localhost:8000/stream.m3u8` やローカル IP を直接プレイヤーに入力してストリーミング動作を確認できます。同一 Wi-Fi 内の別端末（スマホ等）から開く場合は、`--host 0.0.0.0` を付けて起動するか、同梱の `VRCYouTubeStreamer (Local Test).bat` を使用してください（`config.json` の `host` は既定でループバックのみです）。

---

## 🛠 プロジェクト構造

* `streamer_core.py`: ストリーミングエンジン（キュー管理、`yt-dlp`、`ffmpeg`、`cloudflared`、設定管理）
* `api_server.py`: マルチスレッドHTTP APIサーバー（HLS静的配信＋CORS JSON API）
* `gui_streamer.py`: CLI引数解析 & CustomTkinter GUI（ドラッグ＆ドロップ、設定ダイアログ）
* `build_exe.py`: PyInstallerによる単一バイナリ（`dist/VRCYouTubeStreamer.exe`）ビルドスクリプト
* `config.json`: 設定の永続化ファイル
* `FUTURE_PLANS.md`: 将来の機能拡張案・バックログ（ラジオカード画面の自動生成モックアップ等）
