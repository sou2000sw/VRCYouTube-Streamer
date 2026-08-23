# VRCYouTube Streamer

YouTubeの動画・プレイリストをHLSストリーム（`.m3u8`）に変換し、Cloudflare Tunnel経由でVRChatワールド内動画プレイヤー（iwaSync3, YPlay, ProTV等）やブラウザから再生できるようにするストリーミングサーバーです。

GUI画面からの直感的な操作に加え、**外部アプリ（VRCBeacon等）から遠隔操作できるHTTP APIサーバー（ヘッドレスモード）**を備えています。

---

## 🌟 主な機能

1. **デュアル動作モード**:
   * **GUIモード**: CustomTkinter製のダークテーマUIで手動操作
   * **ヘッドレス / APIサーバーモード**: GUIを表示せず、軽量バックグラウンドサーバーとして動作
2. **RESTful HTTP JSON API (CORS対応)**:
   * 外部アプリ（Vue 3, Electron, Node.js, Python等）からHTTPリクエスト経由で状態監視・キュー追加・再生制御・終了が可能
3. **リッチなキュー操作**:
   * **ドラッグ＆ドロップ並び替え**（オートスクロール対応）＋ **「▲」「▼」ボタン**の両立
   * **即時シャッフル (Shuffle List)** & **シャッフル再生モード (Shuffle Play)**
   * **キュー保持ループ再生モード (Loop Queue)**: 再生終了動画を自動でキュー末尾に戻しエンドレス再生
4. **設定管理 (Settings UI & `config.json`)**:
   * サーバーポート、HLSセグメント/バッファ秒数、動画切り替え待機秒数などをGUIおよびAPIから変更・保存可能
5. **Web Player内蔵**:
   * ブラウザから `http://localhost:<port>/` にアクセスするだけで、hls.js を利用したWeb動画プレイヤーで直接プレビュー再生可能

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
  "shuffle": false
}
```
*(※ `status`: `"offline"` / `"buffering"` / `"streaming"` / `"finishing"` / `"error"`)*

---

### 2. キュー追加
* **Method**: `POST`
* **Path**: `/api/queue`
* **Body**:
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```
* **Response**:
```json
{
  "success": true,
  "message": "Successfully added 1 item(s) to queue",
  "video": {
    "title": "Rick Astley - Never Gonna Give You Up",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "duration": 213
  }
}
```

---

### 3. 再生・キュー制御
* **Method**: `POST`
* **Path**: `/api/control`
* **Body アクション一覧**:
  * **スキップ**: `{"action": "skip"}`
  * **キュー全消去**: `{"action": "clear_queue"}`
  * **停止＆キュー消去**: `{"action": "stop"}`
  * **キュー即時シャッフル**: `{"action": "shuffle"}`
  * **ループ再生のON/OFF**: `{"action": "set_loop", "enabled": true}`
  * **シャッフル再生のON/OFF**: `{"action": "set_shuffle", "enabled": true}`
  * **指定インデックスの動画削除**: `{"action": "delete_item", "index": 0}`
  * **動画の並べ替え**: `{"action": "move_item", "from_index": 0, "to_index": 2}`

---

### 4. サーバー終了
* **Method**: `POST`
* **Path**: `/api/shutdown`
* **Response**:
```json
{
  "success": true,
  "message": "Server is shutting down..."
}
```

---

### 5. 設定の取得・更新
* **GET `/api/config`**: 現在の設定JSONを取得
* **POST `/api/config`**: 設定JSONを更新して保存（`config.json` に永続化）
```json
{
  "hls_segment_time": 3,
  "video_transition_wait_seconds": 5,
  "loop_queue": true,
  "shuffle": false
}
```

---

## ⚠️ トラブルシューティング & よくある質問

### 1. トンネルURLが生成されない / 「Tunnel failed to connect」になる
* **原因: Cloudflare Quick Tunnel の一時的な IP レート制限 (Error 1015 / HTTP 429)**
  * 短時間にアプリの起動・再起動を連続して繰り返した場合、Cloudflare 側の無料 Quick Tunnel API（`trycloudflare.com`）によって接続元 IP アドレスに一時的な接続制限（クールダウン）がかけられることがあります。
* **対処法**:
  1. **数分〜10分程度待機する（推奨）**: プロセスを停止した状態で数分待つと、Cloudflare 側のレート制限が自動的に解除され、再び URL が発行されるようになります。
  2. **回線 IP を変更する**: お急ぎの場合は、ルーターの再起動やスマホのテザリング回線に一時切り替えることで即座に再接続が可能です。
  3. **ローカル環境でのテスト**: 同一 PC または同一 Wi-Fi 内での再生テストであれば、トンネル URL ではなく `http://localhost:8000/stream.m3u8` やローカル IP を直接プレイヤーに入力してストリーミング動作を確認できます。

---

## 🛠 プロジェクト構造

* `streamer_core.py`: ストリーミングエンジン（キュー管理、`yt-dlp`、`ffmpeg`、`cloudflared`、設定管理）
* `api_server.py`: マルチスレッドHTTP APIサーバー（HLS静的配信＋CORS JSON API）
* `gui_streamer.py`: CLI引数解析 & CustomTkinter GUI（ドラッグ＆ドロップ、設定ダイアログ）
* `build_exe.py`: PyInstallerによる単一バイナリ（`dist/VRCYouTubeStreamer.exe`）ビルドスクリプト
* `config.json`: 設定の永続化ファイル
