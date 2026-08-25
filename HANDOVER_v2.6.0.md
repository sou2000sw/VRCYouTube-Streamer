# VRCYouTube Streamer v2.6.0 リリース対応 引継ぎ

作成日: 2026-08-25
対象ブランチ: `master`

このセッションで行った v2.6.0 のリリースレビューと不具合修正の引継ぎ資料です。
**コミット済みだが未検証・未ビルドの修正が残っています**（後述「1-2」「3-1」）。まずそこを読んでください。

---

## 1. 現在の状態

### 1-1. コミット済み（6件）

| コミット | 内容 | 検証 |
|---|---|---|
| `d851191` 自動保存 | `api_server.py` — UI正本のfail-closed読込、CORSヘッダ二重送出、`host`設定の握り潰し、LAN端末のホスト権限 | 済 |
| `bca7cb5` 自動保存 | `build_exe.py` / `config.dist.json` / spec / README / CHANGELOG — ui同梱、配布config分離、ZIP除外、ビルド後スモークテスト追加 | 済 |
| `3bbce0b` | CLI引数の`config.json`焼き付き、`verify_release`の残留プロセス | 済 |
| `f22fb10` | 通常動画モード、ラジオ背景セレクト、スライドショー巡回、写真の永続化 | 済 |
| `988c67c` | 画像の一括アップロード、キューの表示専用ソート、HLS再接続（**第1版・不具合あり**） | 一部 |
| `22c348f` 自動保存 | HLS再接続の (a)(b)（下表）、CHANGELOG | **(b) は未検証** |

> `988c67c` 単体に含まれる HLS 再接続は「5回で打ち切って `destroy()`」する実装で、
> **これ自体がプレビューを再生不能にする不具合を持っています**（3-2 参照）。
> `22c348f` で修正済みなので、**その手前のコミットに戻さないでください**。

### 1-2. コードは全てコミット済み。ただし検証状況が分かれる

`22c348f` は Stop フックの自動保存によるコミットで、**検証済みの修正と未検証の修正が
1つのコミットに混ざっています**。

| 修正 | `ui/index.html` | `plugin/ui/index.html` | ビルド済みEXE | 検証 |
|---|---|---|---|---|
| (a) HLS再試行の打ち切り廃止 ＋ `stopLoad()`→`loadSource()` ＋ hls.js内部リトライ上限 | あり | あり | **あり** | **実測済み・PASS** |
| (b) プレビュー開閉まわりの修正（3-1） | **あり** | **なし** | **なし** | **未検証・未ビルド** |

- `ui/index.html` (22:19) = (a) + (b) ← 正本
- `plugin/ui/index.html` (22:01) = (a) のみ。**`ui/` と乖離している**
- `dist/` および `releases/VRCYouTubeStreamer_v2.6.0/` の EXE (22:05) = (a) のみ

判別用マーカー: `ownInstance` / `hlsRetryTimer` / `startLoad(-1)` が (b) 固有。
`ui/index.html` に13箇所、`plugin/ui/index.html` に0箇所。

> **`plugin/ui/index.html` の乖離は手で直さないでください。**
> `build_exe.py` の `package_plugin()` が `ui/index.html` から自動同期するため、
> 次回ビルドで解消されます（4-1 参照）。

### 1-3. 現在の未コミット

```
 M HANDOVER_v2.6.0.md   ← 本ファイル
```

### 1-4. 配布物

`releases/VRCYouTubeStreamer_v2.6.0/` と2つのZIPは **(a) までを含むビルド** です。
ビルド後スモークテスト (`verify_release`) は通過済み。

```
VRCYouTubeStreamer_v2.6.0.zip          : 10ファイル / 実行時生成物の混入なし
vrcbeacon-plugin-vrcyoutube-v2.6.0.zip : 8ファイル  / 実行時生成物の混入なし
config.json は config.dist.json と完全一致
```

---

## 2. 修正済みの不具合（原因と検証）

### 2-1. リリースレビューで発見（配布不可レベル）

**`ui/index.html` が配布物に入っていなかった**
`build_exe.py` の PyInstaller コマンドに `--add-data "ui;ui"` が無く、`create_versioned_release()` も `ui/` をコピーしていなかった。実測: リリースEXEの `GET /` が 22,255 bytes（内蔵テンプレート）、`ui/index.html` は 77,354 bytes。

**内蔵フォールバックテンプレートが破損していた**
`HTML_PLAYER_TEMPLATE` が `<body>` タグ・DOMマークアップ・`<script>` 開始タグごと欠落。`</script>` が4個に対し `<script` が3個。ブラウザで開くとJSがテキスト表示される状態。
→ UIを2箇所に複製する構造自体が原因のため内蔵複製を廃止し、正本が無い場合は診断ページを返す fail-closed 方式に変更。

**プラグインZIPに開発者のアップロード写真が同梱されていた**
`plugin/bin/hls_output/images/photo_*.png` が8枚。`os.walk` で `plugin/` を丸ごと固めていた。
→ `EXCLUDED_DIRS` / `EXCLUDED_FILE_SUFFIXES` で除外。

**`config.json` の `host` 設定が無視されていた**
`bind_host = "" if host in (...) or is_tunnel_disabled` により、トンネル無効時は `"127.0.0.1"` 指定でも `0.0.0.0` で待ち受け、ログ表示も実態と食い違っていた。

**同一LANの端末がホスト権限を持っていた**
トンネル無効時、同一LANの任意の端末が `/api/shutdown`・`stop`・`clear_queue` を実行できた。
→ 管理操作は既定でループバック限定。LAN端末は `allow_web_*` の範囲で操作するゲスト扱い。従来動作は `"trust_lan_clients": true` で明示オプトイン。

**開発用 `config.json` がそのまま配布されていた**（port 8997 / トンネル無効 等）
→ `config.dist.json` を配布用テンプレートの正本として分離。

**CORSヘッダの二重送出** — `end_headers()` と個別ハンドラの双方が付与し `Access-Control-Allow-Origin` が2つ。仕様上クロスオリジン `fetch` が失敗する。

### 2-2. 根本原因の追跡で発見

**CLI引数が `config.json` に焼き付いていた**
`--port` / `--host` / `--no-tunnel` を `self.config` に直接載せていたため、UIから何か設定を変えて `save_config()` が走るたびに永続化されていた。**これが「開発者のローカルテスト設定が配布物の既定値になる」根本原因。**
→ 上書き前の値を baseline として保持し、保存時に元へ戻す。利用者がUIから明示的に変更した項目のみ永続化。

**ビルド後検証のEXEが終了しきらない**
`proc.terminate()` では子プロセスの `ffmpeg` が生き残り `hls_output/` を掴んだまま残留。実測でPID 44728 と ffmpeg 2本が残存。
→ `/api/shutdown` による正規終了を先に実行。

### 2-3. 利用者報告の不具合

**「通常動画」を選んでも音声のみのラジオ再生になる**
モードのトグルが**サーバーへ何も送っていなかった**。`addVideoUrl()` はラジオ時だけ `set_radio_mode:true` を送り、`config` の `radio_mode` 既定が `true` のため初回から通常動画が機能しない。
→ クリック時点で即座に送る `selectAddMode()` を追加。表示は `/api/status` の `radio_mode` に追従させるが、**操作直後3秒間は上書きしない**。
> 追従だけを入れると、2秒間隔のポーリングが選択を巻き戻して「選んでから数秒後に追加を押すと元のモードで再生される」形で再発する（実測済み）。

**ラジオ背景（スライドショー）が切り替わらない** — 原因が2つ重なっていた。
1. UIが `action:"set_radio_bg"` / `background` を送信。サーバー実装は `set_radio_bg_source` / `source` → Unknown action で無視。状態同期も存在しない `data.radio_background` を参照（正しくは `radio_bg_source`）。
2. `atexit` の `cleanup_hls_dir_completely()` と `clean_hls_dir(all_files=True)` が `hls_output/` を再帰削除し、**アップロード写真とラジオカードキャッシュを起動・終了のたびに全消去**していた。写真0枚ではスライドショーは待機画面にフォールバックする。
→ `images/` を保持するよう変更。実測: 修正前 6→0→0枚、修正後 6→6→6枚。

**画像が表示されずに飛ばされる**
`concat` + `-stream_loop -1` は常にマニフェスト先頭から再生されるため、`写真枚数 × 表示秒数 > 曲の長さ` のとき後半の写真が表示されないまま次の曲でまた1枚目に戻る。実測: 写真8枚×5秒=40秒 vs 19秒の曲 → 毎回1〜4枚目だけ。
→ 曲ごとに開始位置をずらし、消化枚数分カーソルを進めて巡回。実測: `#1 → #5 → #3 → #1`。

**画像の一括アップロードで1枚しか登録されない**
`/api/upload` に「2.5秒に1回」の最小間隔レートリミットが掛かっており、複数枚を連続POSTすると2枚目以降がすべて `429`。
実測（修正前）: ループバック `200 200 200 200 200 200` / LAN `200 429 429 429 429 429`
→ 時間枠内の合計枚数方式（既定 20枚/60秒）へ変更。実測（修正後）: LAN 6枚すべて200、+16枚で20枚到達後に429。
> `is_local_request` をループバック限定に絞った際、従来ホスト扱いだったLANがこの制限の対象に入ったのが顕在化の契機。トンネル経由では以前から同じ症状だったはず。

### 2-4. 追加した機能

**再生キューの表示専用ソート／絞り込み**（利用者要望「表示上だけでOK」）
- 絞り込み: すべて / 動画のみ / 画像のみ（`selectQueueFilter`）
- 並べ替え: 再生順 / タイトル昇順・降順 / 長さ昇順・降順 / 種別順（`selectQueueSort`）
- **サーバー上の再生順は変更しない**。件数バッジは絞り込み時 `表示件数 / 全件数` に切替。
- 移動・削除APIは実キューの添字で動くため、実添字を保持して描画する。
- **既定表示（すべて / 再生順）以外ではドラッグと上下移動を無効化**。画面上の隣と実キューの隣が一致せず意図しない位置へ動くため。削除は表示順に依存しないので有効のまま。

---

## 3. 未解決・要対応

### 3-1.【最優先】未検証の (b) プレビュー開閉修正

`22c348f` でコミット済みですが、**ビルドもテストもしていません**。内容:

1. `hlsRetryTimer` を保持し、`initHlsPlayer()` で作り直す際に `clearTimeout()` する
2. `const ownInstance = hlsInstance` を捕捉し、`MANIFEST_PARSED` / `ERROR` ハンドラと再接続タイマー内で `hlsInstance !== ownInstance` なら早期 return
3. `toggleLivePreview()` を変更 — 閉じる時に `stopLoad()`、開く時は作り直さず `startLoad(-1)` で再開

**動機となった実測値**（サブエージェントによる受け入れテスト P5）:

| 経過 | readyState | currentTime | hlsFatalRetries | videoStatusText |
|---|---|---|---|---|
| 開き直し直後 | 1 | 0 | 7 | 再接続中... (7) |
| +8s | 4 | 65.36 | 11 | 再接続中... (11) |
| +16s | 1 | 0 | 14 | 再接続中... (14) |
| +40s | 4 | 166.50 | 16 | 再接続中... (16) |
| +104s | 4 | 327 | 16 | **再接続中... (16) のまま** |

判明している問題は2点。
- プレビューを開き直すと復帰まで約40秒かかり、`hlsFatalRetries` が 7→16 まで積み上がる
- 映像は復帰しているのに `videoStatusText` と `hlsFatalRetries` がリセットされない（`MANIFEST_PARSED` の成功時リセットがこの経路で効いていない）

推定原因: 破棄済みインスタンス宛ての `setTimeout` が後から発火し、モジュールスコープの `hlsInstance`（＝新しいインスタンス）に対して `stopLoad()`/`loadSource()` を撃ち込んでいる。(b) はこれを潰す意図の修正。

**この推定は未検証です。** 再開時はまず 4-2 の手順で実測してください。

### 3-2. HLS再接続に「打ち切り」を再導入してはいけない

`988c67c` の HLS 再接続は「5回で打ち切って `destroy()`」する実装で、これ自体が不具合でした。
`22c348f` の (a) で撤廃済みですが、ポート枯渇対策として再度入れたくなる形なので理由を残します。

サーバーは起動直後、`/stream.m3u8` が**約12秒間 404** を返します（待機画面のFFmpegが立ち上がるまで）。この窓でページを開くと、`startLoad()` は**マニフェストを一度も取得できていない状態では何も再取得しない**ため1回目の再試行で停止し、その後配信が始まっても復帰しません。

実測（修正前）: 50秒後 `readyState=0, paused=true, currentTime=0, buffered=0`, statusText `再接続中... (1/5)`
実測（(a) 修正後）: 45秒後 `readyState=4, paused=false, currentTime=55.26, buffered.end=57, 1920x1080`, statusText `ライブ再生中`, retries 0

打ち切りは**入れてはいけません**。曲の切り替わりでも一時的に404になるため、`destroy()` すると二度と復帰しません。

### 3-3. 単一セグメントへの404連打（未修正）

P5 のテスト中、プレビュー再オープン直後に `seg_00177.ts` へ **404が約100回連続**で発行される現象を観測。バックオフなしのタイトループ。ポート枯渇には至らなかったが、`net::ERR_ADDRESS_IN_USE` を起こしていた旧不具合と同系統。
推定原因: 閉じている間にライブウィンドウから消えたセグメントを追いかけている。(b) の `startLoad(-1)` はこれも狙って入れているが未検証。

### 3-4. 検証できていない項目

- **起動直後404窓でのプレビュー自動復帰（配布EXE）** — サブエージェントに渡すまでに404窓が過ぎてしまい判定不能。(a) はソース起動では実測済みだが、配布EXEでは未確認。
- `test_transition.py` — 起動中サーバー前提のため環境依存で失敗する（コード不具合ではない）。

### 3-5. 対応を見送った事項

- **ヘッダーの「停止」ボタン** — [ui/index.html](ui/index.html) の `handleStopServer()` が `POST /api/shutdown` を送る、すなわち**サーバープロセスごと終了**する。ラベルからは「配信の停止」と読めるため、確認ダイアログの追加かラベル変更（例:「サーバー終了」）を検討する価値あり。実際にテスト中の別エージェントが誤って押してサーバーを落とした。
- **`btnSkip` の二重POST疑い** — ソース上は再現しない。inline `onclick` 1つのみで `addEventListener` もクリック委譲も無く、計測方法を変えた再テストでは 1クリック＝1POST だった。最初の報告は `fetch` をラップした計測の副作用。
- **`/api/control` の `set_image_duration`** — パラメータ名を間違えると400ではなく**既定値15秒で黙って上書き**する。UI以外から叩くと事故る。
- **キュークリア／スキップしても再生が止まらない** — `loop_queue: true` により最後の動画がループするため。設定どおりの挙動。

---

## 4. 作業再開の手順

### 4-1. ビルドとパッケージング

```bash
python build_exe.py
```

`releases/VRCYouTubeStreamer_v{version}/` と2つのZIPを生成し、最後に `verify_release()` が
実際にEXEを起動して `GET /` を検証します（UI正本との一致・`<script>`の開閉整合・`<body>`の存在・
CORSヘッダ重複）。失敗するとビルドが異常終了します。

`plugin/ui/index.html` は `package_plugin()` が `ui/index.html` から自動同期するため、
手で編集しないでください。

### 4-2. プレビューの検証（3-1 の確認手順）

起動直後の404窓を再現する必要があります。

```bash
cd releases/VRCYouTubeStreamer_v2.6.0 && ./VRCYouTubeStreamer.exe --headless --no-tunnel --port 8996 --host 127.0.0.1
```

起動したら `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8996/stream.m3u8` が
**404 のうちに**ブラウザでページを開きます。60秒後に以下を確認:

```js
(function(){const v=document.getElementById('liveVideo');return JSON.stringify({
  readyState:v.readyState, paused:v.paused, currentTime:v.currentTime,
  buffered:v.buffered.length, retries:hlsFatalRetries,
  statusText:document.getElementById('videoStatusText').innerText});})()
```

期待値: `readyState >= 3` / `paused: false` / `currentTime` 増加 / `retries: 0` / `ライブ再生中`

続けてプレビューの開閉（`btnTogglePreview` を2回）を行い、**開き直した直後から10秒以内に**
上記が正常値へ戻ること、`hlsFatalRetries` が積み上がらないことを確認してください。

### 4-3. 単体テスト

```bash
python -m pytest test_security.py test_radio_unit.py -q
```

現状 4 passed。`test_transition.py` は 3-4 のとおり環境依存で失敗します。

---

## 5. この作業で踏んだ罠

**ブラウザは必ずハードリロード（Ctrl+Shift+R）する**
再検証時、リロード前のタブが旧UIのままで誤ったFAIL判定が出ました。サーバーは
`Cache-Control: no-cache, no-store, must-revalidate` を返しているため、
キャッシュではなく単に「タブを再読込していない」ことが原因です。

**サーバーは起動直後の十数秒 `/stream.m3u8` が404を返す**
プレビュー関連の検証は、この窓の内と外の両方で行わないと片方を見落とします。
実際、(a) の検証を「配信が既に始まっている状態」でしか行わなかったために
打ち切り実装の欠陥を見逃しました。

**ブラウザ検証をサブエージェントに任せる場合の禁止事項**
- ヘッダーの「停止」「再起動」ボタンと `/api/shutdown` を明示的に禁止する（3-5）
- `window.fetch` のラップを禁止する（`btnSkip` 二重POST の誤検出を招いた）
- `hlsInstance` の `destroy()` / 差し替えを禁止する（計測が壊れる）
- `javascript_tool` は `(function(){...})()` で囲ませる（`const` 再宣言エラー回避）
- Browser ペインが非表示のため `screenshot` は失敗し `read_page` も空を返す旨を伝える

**検証で書き換わる設定を戻す**
`/api/config` や `set_image_duration` を叩くと `config.json` が実際に書き換わります。
ルートの `config.json` は `.gitignore` 対象なので diff に出ません。検証後に元の値へ戻すこと。

**`hls_output/images/` は消さない**
2-3 の修正により、アップロード写真とラジオカードキャッシュは意図的に永続化されます。
配布物への混入は `build_exe.py` の除外リストで防いでいるので、手で消す必要はありません。

---

## 6. 参照

- 変更履歴: [CHANGELOG.md](CHANGELOG.md) の `[2.6.0]` セクション
- プラグイン連携: [plugin/BEACON_BRIDGE_HANDOVER.md](plugin/BEACON_BRIDGE_HANDOVER.md)
- 配布用設定の正本: [config.dist.json](config.dist.json)
