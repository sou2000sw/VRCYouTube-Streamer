# VRC_Media_Streamer

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**面倒なサーバー構築やエンコード知識は不要。**
**EXEを起動してURLを貼るだけで、ワールド内の動画プレイヤーにYouTubeが流れ始めます。**

※ 無料枠と有料枠（支援用）の内容は完全に同一です。お金を払っても機能やサポートは増えませんのでご注意ください。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 【ツール概要】

『**VRC_Media_Streamer**』は、YouTubeの動画・プレイリストを自分専用のHLSライブストリーム（`.m3u8`）に変換し、VRChat内の各種動画プレイヤー（iwaSync3, YPlay, ProTV, YamaPlayer 等）でシームレスに再生するためのWindowsアプリケーションです。

もともと作者が自分で使うために個人的に作成したものです。
AIバイブコーディング製のため手厚いサポートはできませんが、「動いたらラッキー」くらいの気持ちで気軽にご利用ください。

- **ソースコード / GitHub**: [https://github.com/sou2000sw/VRCYouTube-Streamer](https://github.com/sou2000sw/VRCYouTube-Streamer)

---

## ✨ 主な機能と特徴

* **起動してURLを貼るだけ — 事前準備ゼロ**
  Python・FFmpeg・その他ランタイムの事前インストールは一切不要です。ZIPを解凍して EXE を起動するだけですぐに使えます。
* **YouTube動画＆プレイリストの連続再生**
  YouTube URLを入力するだけで、動画の取得 → HLS変換 → ストリーミング配信を自動で行います。プレイリストURLを入れれば一括展開＆連続再生されます。
* **キューのドラッグ＆ドロップ並び替え**
  各行の「☰」マークまたはタイトルをドラッグして直感的に順番を変更できます。リストの上下端に持っていくと自動スクロール。「▲」「▼」ボタンも併用可能です。
* **ループ再生＆シャッフル再生**
  - 🔁 **Loop**: 再生終了した動画をキュー末尾に自動再登録しループ再生。
  - 🔀 **Shuffle**: キューからランダムに次の曲を選出して再生。ループと併用でランダム巡回も可能。
  - 🔀 **Shuffle List**: 現在のキューを一瞬でランダム順に並べ替え。
* **Cloudflare Tunnel で自動URL発行（設定不要）**
  起動するだけで外部アクセス可能なストリームURLが自動生成されます。ポート開放やDDNSの設定は不要です。生成されたURLをVRChat内の動画プレイヤーに貼るだけで共有できます。
* **📱 スマホQRコードでフレンドからリクエスト受付**
  キューが空になると、待機画面にQRコード＆WebURLが表示されます。フレンドがスマホで読み取ると、Webリモコン画面から動画のリクエストを送れます。アプリ画面上にもQRコード＆WebURLは常時表示されています。
* **🌐 Webリモコン＆ブラウザ再生**
  ブラウザで `http://localhost:8000/`（またはトンネルURL）にアクセスすると、HLS Web Player による配信プレビューとキュー操作・動画/写真追加が可能です。スマホ縦画面にも最適化されたレスポンシブUIです。
* **📻 BGM / ラジオモード（超低帯域配信 & サムネイル自動生成）**
  YouTube動画から高音質音声ストリームのみを抽出し、自動生成された「サムネイル＆楽曲情報カード画面」（または待機画面/写真スライドショー）と合成して超低帯域（約250〜350kbps、通常動画比90%以上削減）でHLS配信。VRChatでのバッファ詰まりや多人数インスタンスでの遅延を極小化します。
* **🖼️ 写真・画像アップロード＆スライドショー配信**
  スマホやPCから複数枚の画像（JPEG, PNG, WebP等）をまとめてキューへ追加可能。表示秒数切り替え（5s〜120s）や自動送りON/OFFをGUI/Webリモコンからリアルタイム操作できます。
* **⚙ 設定画面 (Settings)**
  サーバーポート、HLSセグメント秒数、動画切り替え待機秒数、Web Player同期バッファ数、Loop/Shuffleのデフォルト設定などをGUIから変更・保存可能。設定画面内にAPI仕様リファレンスも内蔵。
* **🤖 ヘッドレス / APIサーバーモード**
  GUIを表示せずバックグラウンドで動作するAPIサーバーモードを搭載。外部アプリからHTTP JSON API経由で状態取得・キュー追加・再生制御が可能です。
* **🎬 多様な動画元・SNSプラットフォームに対応（実機検証済み）**
  YouTube動画だけでなく、YouTubeショート、YouTubeライブ、X（旧Twitter）動画、Instagramリール動画等、幅広いWeb動画の再生に対応しています。

---

## 🎬 実機動作確認済みの対応動画元・プラットフォーム

内部の `yt-dlp` 解析エンジンにより、以下の動画・配信サービスからのURL抽出およびストリーミング配信が実機で動作確認されています：

| プラットフォーム / ソース | 対応状況 | 補足・詳細 |
|---|---|---|
| **YouTube 通常動画** | ✅ **対応** | 通常動画URL、短縮URL (`youtu.be`)、再生リスト一括追加に対応 |
| **YouTube Shorts（ショート動画）** | ✅ **対応** | `youtube.com/shorts/...` URLをそのままキューへ投入可能 |
| **YouTube Live（ライブ配信）** | ✅ **対応** | 進行中のYouTubeライブ配信のリアルタイム中継・同期配信に対応 |
| **X (旧 Twitter) 動画** | ✅ **対応** | ポスト（ツイート）に含まれる動画URLの自動抽出・再生に対応 |
| **Instagram (インスタグラム) 動画 / Reels** | ✅ **対応** | 投稿動画およびリール（Reels）動画の再生に対応 |
| **Twitch (ツイッチ)** | ⚠️ **一部対応** | 配信チャンネル・クリップにより再生できるものと再生できないものがあります（仕様・DRM等の差異により一部制限あり） |
| **ニコニコ動画** | ❌ **非対応** | ニコニコ動画のURLは現在ご利用いただけません（非対応） |
| **静止画 / 写真ファイル** | ✅ **対応** | JPEG, PNG, WebP 等の写真アップロードおよびスライドショー配信 |

---

## 📦 導入方法

1. **ZIPを展開し、フォルダごと書き込み可能な場所に配置してください。**
   （例: デスクトップ、ドキュメント、`D:\Tools\` など）
   > [!WARNING]
   > `C:\Program Files` や `C:\Program Files (x86)` 直下では権限の都合上、正常に動作しません。必ずユーザー権限で書き込み可能なフォルダに配置してください。

2. **「`VRC_Media_Streamer.exe`」（または同梱のバッチファイル）を起動する。**

3. **VRChat側の設定を確認する**
   VRChat内のメニューで「信頼されていないURLを許可 (Allow Untrusted URLs)」を有効にしてください。
   （設定: `Settings` ＞ `Downloads & Share` または `快適性とセーフティ`）

> [!NOTE]
> 初回起動時に Windows SmartScreen の警告（「WindowsによってPCが保護されました」）が出る場合があります。個人開発のためコード署名を行っていないことが原因です。「詳細情報」をクリックし、「実行」を選択して起動してください。

---

## 📦 内容物

- `VRC_Media_Streamer.exe`（本体アプリケーション）
- `ffmpeg.exe`（動画変換エンジン／同梱必須・同じフォルダに置いてください）
- `VRC_Media_Streamer (Normal).bat`（通常起動バッチ）
- `VRC_Media_Streamer (Local Test).bat`（ローカル検証用バッチ）
- `VRC_Media_Streamer (Headless Test).bat`（ヘッドレスAPIサーバー用バッチ）
- `README.txt` / `README.md`（説明書）
- `FFmpeg_LICENSE.txt` / `THIRD_PARTY_LICENSES.txt`（ライセンス表記）

---

## 💻 動作環境

- **対応OS**: Windows 10 / 11 (64bit)
- **ネットワーク**: 安定したインターネット接続（アップロード帯域を使用します）
- **VRChat側**: iwaSync3, YPlay, ProTV, YamaPlayer, KineLister 等、HLS（.m3u8）対応のワールド動画プレイヤー
- **事前インストール**: 不要（必要なランタイム・バイナリは同梱済み）

---

## 🚀 起動方法・起動オプション

### 1. GUIモードで起動
```bash
VRC_Media_Streamer.exe
# または開発時:
python gui_streamer.py
```

### 2. ヘッドレス / APIサーバーモードで起動
```bash
VRC_Media_Streamer.exe --headless --port 8080
# または開発時:
python gui_streamer.py --headless --port 8080
```

#### コマンドライン引数一覧
| 引数 | 説明 | デフォルト値 |
| :--- | :--- | :--- |
| `--headless` / `-hl` | GUIを起動せずバックグラウンドAPIサーバーとして動作 | なし (GUI起動) |
| `--no-tunnel` / `-nt` | Cloudflareトンネルを起動せずローカルテストモードで動作 | なし (トンネル起動) |
| `--tunnel` | Cloudflareトンネルを明示的に有効化 | 有効 (デフォルト) |
| `--port` / `-p` | APIサーバーおよびHLS配信サーバーのポート番号 | `8000` (または `config.json`) |
| `--host` | サーバーのホストアドレス (LAN内共有時は `0.0.0.0`) | `127.0.0.1` |

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

### 2. キュー追加 (URL)
* **Method**: `POST`
* **Path**: `/api/queue`
* **Body**: `{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}`

### 3. 写真・画像アップロード (単一・複数対応)
* **Method**: `POST`
* **Path**: `/api/upload`
* **Content-Type**: `multipart/form-data` または `image/*`
* **Body**: 画像バイナリ（単一ファイル、または `files[]` による複数ファイル一括送信、最大20MB/ファイル）

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

### 5. 接続用 QR コード画像取得
* **Method**: `GET`
* **Path**: `/api/qrcode`
* **Response**: PNG 画像ストリーム

### 6. 設定の取得・更新
* **GET `/api/config`**: 現在の設定JSONを取得
* **POST `/api/config`**: 設定JSONを更新して保存（`config.json` に永続化）

### 7. サーバー終了
* **Method**: `POST`
* **Path**: `/api/shutdown`

---

## ℹ️ 仕様・制限事項

- **URLの再生成**: Cloudflareの一時トンネルを使用しているため、ツールを再起動するたびにストリームURLが変わります。起動中は同じURLで利用できます。
- **YouTubeの仕様変更**: YouTube側の更新により、動画の取得やプレイリストの展開が一時的にできなくなることがあります。
- **ウイルス対策ソフトの誤検知**: コード署名を行っていないため、一部のウイルス対策ソフトが誤検知する場合があります。
- **短時間の大量リクエストによる一時制限**: 短時間に大量の動画URLを連続追加したり、巨大なプレイリストを一気に読み込ませると、YouTube側またはCloudflare側から一時的なアクセス制限（レートリミット / 429エラー）がかかり、一時的に動画が取得できなくなる場合があります。その場合は連投を控え、数分〜10分程度時間を置いてから再度お試しください。（※制限の解除を待つか、回線IPの変更で復旧します）
- **推奨用途**: 本ツールは常時稼働を想定したものではありません。ワールド内プレイヤーの不調時やURLが読み込めない場合など、一時的なトラブル回避や個人・少人数での検証用途としての利用を推奨します。

---

## ∥ 免責事項

- **個人開発**: 本ツールは個人が自分用に開発したものを公開しているものであり、商用製品ではありません。
- **自己責任の原則**: 本ツールの使用によって生じたいかなる損害・損失・トラブルについて、製作者は一切の責任を負いません。自己責任においてご利用ください。
- **動作保証の範囲**: 特定の環境・動画・プレイリストでの動作を完全に保証するものではありません。作者の環境ではだいたい動いています。
- **外部サービスへの依存**: YouTube・Cloudflareなど外部サービスの仕様変更・障害により、ツールの機能が利用できなくなる場合があります。これらは製作者の管理外です。
- **サポートについて**: 個人の趣味開発のため、不具合報告は受け付けますが、対応時期や修正をお約束するものではありません。
- **非公式ツール**: 本ツールはYouTube・VRChat・Cloudflareの公式ツールではありません。各サービスの利用規約は利用者ご自身でご確認ください。

---

## ⚖️ ライセンス / LICENSE

本パッケージには、動画変換処理を行う外部ツールとして **FFmpeg（GPL v3）** の実行ファイルが同梱されています。本アプリはFFmpegのバイナリを改変せず、独立した外部プロセスとして呼び出しています。
→ 詳細は同梱の「`FFmpeg_LICENSE.txt`」を参照してください。

その他、以下のオープンソースソフトウェア・ライブラリを利用しています：
- **cloudflared** (Apache-2.0)
- **yt-dlp** (The Unlicense)
- **Python / Tcl/Tk**
- **CustomTkinter** (MIT License)
- **Pillow** (HPND License)
- **qrcode** (BSD License)
- **hls.js** (Apache-2.0)
→ 詳細は同梱の「`THIRD_PARTY_LICENSES.txt`」を参照してください。
