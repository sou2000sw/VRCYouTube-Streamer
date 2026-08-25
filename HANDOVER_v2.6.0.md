# v2.6.0 リリース対応 引継ぎ書

作成日: 2026-08-25
対象ブランチ: `master`
最終コミット: `988c67c fix(upload): 画像の一括アップロードを修正 ＋ キューに表示専用ソートを追加`

---

## 1. いま何が起きているか（最重要）

### 作業ツリーに**未コミット・未検証**の変更が残っています

```
 M CHANGELOG.md          (+7/-2)
 M ui/index.html         (+83/-21)   ← 未検証の修正を含む
 M plugin/ui/index.html  (+39/-11)   ← ビルド時の自動同期分（古い）
```

`ui/index.html` と `plugin/ui/index.html` は**内容が食い違っています**。`plugin/ui/index.html` はビルド時に `ui/index.html` からコピーされるため、次回ビルドで自動的に揃います（手で直さないこと）。

### ビルド済み成果物との対応関係

| 対象 | 含まれている修正 |
|---|---|
| `releases/VRCYouTubeStreamer_v2.6.0/` の EXE と ZIP | コミット済みの全修正 ＋ 「プレビュー再試行の打ち切り撤廃」まで（**検証済み**） |
| `ui/index.html` の未コミット分 | 上記に加えて **§3 の P5 対策3点（未検証）** |

**つまり配布物は「検証済みの状態」で止まっています。** 未コミット分をリリースに反映したい場合は、§4 の手順でビルドと検証をやり直してください。

### 選択肢

- **A. 未コミット分を採用する** → §4 の手順でビルド → §5 の検証 → コミット
- **B. 未コミット分を捨てる** → `git checkout -- ui/index.html plugin/ui/index.html CHANGELOG.md`
  （配布物は既に検証済みの状態なので、これでも整合します）

未コミット分は「P5 で見つかった実在不具合の修正」なので、**A を推奨**します。ただし一度も動かしていないコードです。

---

## 2. このセッションで修正したもの（コミット済み）

### `d851191` / `bca7cb5`（自動保存コミット）— リリースレビュー指摘

| 指摘 | 原因 |
|---|---|
| `ui/index.html` が配布物に無い | PyInstaller に `--add-data "ui;ui"` が無く、`create_versioned_release()` も ui/ をコピーしていなかった |
| 内蔵フォールバックHTMLが破損 | `HTML_PLAYER_TEMPLATE` に `<body>` と `<script>` 開始タグが欠落。配信されるとJSがテキストとして画面に出る |
| プラグインZIPに開発者の写真8枚 | `plugin/` を丸ごとzipしており、実行時生成物 `plugin/bin/hls_output/` が混入 |
| `config.json` の `host` が無視される | トンネル無効時に `host` を握り潰して `0.0.0.0` バインド。ログ表示も実態と不一致 |
| 同一LANの端末がホスト権限を持つ | `is_local_request()` がLAN全体をホスト扱いし、誰でも `/api/shutdown` を叩けた |
| 開発用configがそのまま配布 | `config.dist.json` を配布用テンプレートとして分離 |
| CORSヘッダ二重送出 | `end_headers()` と個別ハンドラの双方が付与 |

**対策として `build_exe.py` にビルド後スモークテスト `verify_release()` を追加しました。** 実際にEXEを起動して `GET /` を取得し、UI正本との一致・`<script>` タグの開閉整合・`<body>` の存在・CORS重複を検査します。上記の致命的2件はこれで自動検出できます。

### `3bbce0b` — CLI引数のconfig焼き付き

`--port` / `--host` / `--no-tunnel` を `self.config` に直接載せていたため、UIから何か設定を変えて `save_config()` が走るたびに永続化されていました。**これが「開発者のローカル設定が配布物の既定値になる」根本原因**です。上書き前の値を baseline として保持し、保存時に元へ戻すようにしています。

あわせて `verify_release()` の後始末を `/api/shutdown` による正規終了に変更しました。`proc.terminate()` では子の ffmpeg が生き残り、`hls_output/` を掴んだままビルドごとに残留していました。

### `f22fb10` — 再生モード・スライドショー

| 症状 | 原因 |
|---|---|
| 通常動画モードが効かない | `addVideoUrl()` が radio のときだけ `set_radio_mode:true` を送り、video では無送信。`config` の `radio_mode` 既定が `true` なので初回から機能していなかった |
| ラジオ背景の切替が効かない | UI が `action:"set_radio_bg"` / `background` を送信、サーバー実装は `set_radio_bg_source` / `source`。Unknown action で無視。状態同期も存在しない `data.radio_background` を参照 |
| スライドショーが空になる | `atexit` の `cleanup_hls_dir_completely()` と `clean_hls_dir(all_files=True)` が `hls_output/` を再帰削除し、**利用者の写真とラジオカードキャッシュまで毎回消していた** |
| 一部の画像が表示されない | `concat` + `-stream_loop -1` が毎曲必ず1枚目から再生するため、`枚数 × 秒数 > 曲の長さ` だと後半が永久にスキップされる |

> **落とし穴**: モード表示をサーバー状態に追従させるだけだと、2秒間隔のポーリングがユーザーの選択を巻き戻し、**選んでから数秒後に追加すると元のモードで再生される**という形で再発します。トグルのクリック時点で即座に `set_radio_mode` を送る `selectAddMode()` にし、操作後3秒はポーリングの上書きを抑止して解決しています。

### `988c67c` — 一括アップロード・キュー表示ソート

| 項目 | 内容 |
|---|---|
| 一括アップロードが1枚しか通らない | `/api/upload` に「2.5秒に1回」の最小間隔制限。時間枠内の合計枚数方式（既定 20枚/60秒）へ変更 |
| キューの表示ソート | 絞り込み（すべて/動画/画像）＋並べ替え（再生順/タイトル/長さ/種別）を追加。**表示専用でサーバーの再生順は変更しない** |

> **注意**: 一括アップロードの不具合は**ループバック（`localhost`）では再現しません**。LAN・トンネル経由でのみ発生します。`is_local_request()` をループバック限定に絞った際、従来ホスト扱いだったLANが制限対象に入ったのが顕在化の契機でした。

> **設計判断**: 既定表示（すべて／再生順）以外のときは、画面上の隣と実キューの隣が一致せず意図しない位置へ動くため、**ドラッグと上下移動を無効化**しています。削除は表示順に依存しないので有効のままです。移動・削除APIは実キューの添字で動くため、描画時に実添字を保持しています（`buildQueueView()`）。

---

## 3. 未解決の課題

### 3-1. 【未検証の修正あり】プレビューを開き直すと復帰に約40秒かかる

サブエージェントのブラウザテスト P5 で検出。`btnTogglePreview` で閉じて開き直すと:

```
開き直した直後(12秒後): readyState=1, currentTime=0, buffered=0, 解像度 0x0, hlsFatalRetries=7
+16s〜+32s:            readyState=1, currentTime=0        （約40秒この状態）
+40s以降:              readyState=4, currentTime 166→327  （再生自体は復帰する）
```

**さらに、映像が復帰しても `videoStatusText` が `ストリーム待機中 / 再接続中... (16)` のまま固定され、`hlsFatalRetries` も 16 のままリセットされません。**

推定原因（**未確認**）:
1. 破棄済み `hlsInstance` 宛ての再接続 `setTimeout` が後から発火し、モジュールスコープの `hlsInstance`（＝新インスタンス）に対して `stopLoad()`/`loadSource()` を撃ち込んでいる
2. 破棄済みインスタンスのイベントハンドラが `hlsFatalRetries` と `statusText` を書き換え続けている
3. 閉じている間も裏でセグメントを取得し続け、再生位置が古くなる

`ui/index.html` に**未コミット・未検証**の対策を書いてあります:

| 対策 | 実装箇所 |
|---|---|
| `hlsRetryTimer` を保持し、`initHlsPlayer()` で必ず `clearTimeout` | 611行目付近 / 682行目付近 |
| `const ownInstance = hlsInstance` を捕捉し、ハンドラ冒頭で `if (hlsInstance !== ownInstance) return;` | 708 / 716 / 728 / 749行目付近 |
| プレビューを閉じたら `stopLoad()`、開くときは作り直さず `startLoad(-1)` | `toggleLivePreview()` |

**一度も動かしていません。** §5 の P5 手順で必ず検証してください。

### 3-2. 単一セグメントへの404連打（約100回）

同じくP5で観測。プレビュー再オープン直後、`seg_00177.ts` に対して404がバックオフなしで約100回連続発行されました（`stream.m3u8` は全件200、他セグメントも200、その後 `seg_00196` 以降は200で回復）。

閉じている間にライブウィンドウから消えたセグメントを追いかけているためと推定されます。3-1 の `startLoad(-1)`（ライブ先頭から読み直す）で解消する見込みですが**未確認**です。ポート枯渇には至っていません。

### 3-3. 「404の最中にページを開いた場合」の配布EXEでの再検証が未完了

サーバーは起動直後の約12秒間 `/stream.m3u8` が404を返します。この窓でページを開くケースは**ソース実行では修正を確認済み**ですが、配布EXEでの受け入れテストではサブエージェントが窓に間に合わず**判定不能**のままです。

再現手順は §5 の P1 にあります。EXE起動から**十数秒以内**にページを開く必要があります。

### 3-4. 判断保留（機能面・未着手）

| 項目 | 内容 |
|---|---|
| ヘッダー「停止」ボタン | `handleStopServer()` が `POST /api/shutdown` を送り、**EXEプロセスごと終了**します。ラベルから「配信の停止」と読めるため、確認ダイアログか「サーバー終了」への改名を検討する価値あり |
| `set_image_duration` の寛容さ | パラメータ名を間違えると400ではなく**既定値15秒で黙って上書き**します。UI以外から叩くと事故ります |
| キュークリア／スキップで再生が止まらない | `loop_queue: true` により最後の動画がループするため。設定どおりの挙動 |
| `btnSkip` の二重POST疑い | 初回のサブエージェントが報告しましたが、ソース上は inline `onclick` 1つのみでクリック委譲もなく**再現しません**。計測フックの副作用と判断し未修正。実機で「1回で2曲進む」事象があれば要調査 |

---

## 4. ビルド手順

```bash
cd E:\Projects\VRCYouTube
python -m pytest test_security.py test_radio_unit.py -q   # 4 passed が正常
python build_exe.py                                        # 数分かかる
```

`build_exe.py` は最後に `verify_release()` を自動実行します。以下が出れば成功です。

```
[OK] Served UI: NNNNN chars, script tags balanced (4/4).
[OK] CORS headers are not duplicated.
[OK] Release package verified.
```

ビルド後に必ず確認すること:

```bash
# 残留プロセス（0 であること）
netstat -ano | grep -E ":899[0-9].*LISTENING"
# 配布物（本体10ファイル / プラグイン8ファイル、hls_output と photo_ が無いこと）
python -c "import zipfile;print(zipfile.ZipFile('releases/VRCYouTubeStreamer_v2.6.0.zip').namelist())"
# 配布 config がテンプレートと一致すること
```

`test_transition.py` は起動中サーバーを前提とするため単独では失敗します（環境依存でコード不具合ではありません）。

---

## 5. 検証手順（ブラウザ）

**ブラウザテストはサブエージェントに委譲する運用**です。以下をプロンプトに必ず含めてください。

### サブエージェントへの禁止事項（過去に事故あり）

- **`btnHeaderStop` / `btnHeaderRestart` を押させない。** `POST /api/shutdown` でEXEごと落ちます（1回目のテストで実際に落ちました）
- **`window.fetch` をラップさせない。** 2回目のテストで「`btnSkip` が2回POSTしている」という誤検出が出ました。送信確認は `read_network_requests` を使わせること
- **`hlsInstance` を触らせない。** 3回目のテストで計測のため `destroy()` され、状態が壊れました
- `javascript_tool` は毎回 `(function(){ ... })()` で囲ませる（`const` 再宣言エラー回避）
- Browser ペインは非表示のため `screenshot` は失敗し、`read_page` も空を返します

### 検証項目

**P1. 配信開始前に開いても自動復帰するか（未完了・最優先）**

EXEを起動し、`/stream.m3u8` が404を返している**十数秒の間に**ページを開く。60秒後に `readyState >= 3` / `paused: false` / `currentTime` 増加 / `videoStatusText === 'ライブ再生中'` / `hlsFatalRetries === 0` になれば PASS。
**`readyState: 0` や `paused: true` のままなら FAIL。**

**P5. プレビューの開閉（未検証の修正あり・最優先）**

`btnTogglePreview` で閉じる → 5秒待つ → 開き直す。開いた直後から10秒以内に `readyState >= 3` / `currentTime` 増加 / `videoStatusText === 'ライブ再生中'` / `hlsFatalRetries === 0` になれば PASS。
あわせて `read_network_requests` で**同一セグメントへの404連打が起きていないこと**を確認。

**回帰確認（いずれも直近で PASS 済み）**

| # | 内容 | 期待値 |
|---|---|---|
| 通常動画 | `modeVideoBtn` を押し**8秒待ってから**追加 | `status_detail: "Active (Streaming)"`、タイトルに 📻 が付かない |
| ラジオ | `modeRadioBtn` を押し8秒待ってから追加 | `status_detail: "Active (Radio BGM)"`、`📻 Me at the zoo` |
| ラジオ背景 | `selectRadioBg` を slideshow / standby に変更 | `/api/status` の `radio_bg_source` が追従、リロード後も維持 |
| 一括アップロード | canvas で5枚生成し `handleImageFiles(files)` | `POST /api/upload` 5件すべて200、429なし |
| キュー表示ソート | フィルタ・ソートを切替 | `/api/status` の `queue` 順序が不変、`move_item` が送られない |
| 添字ずれ | フィルタ表示の2行目を削除 | その項目だけが消える |

### コマンドラインでの確認

```bash
# 配信の生存確認
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8996/stream.m3u8   # 起動直後は404、十数秒後に200
curl -s http://127.0.0.1:8996/api/status

# LAN経由の一括アップロード（ループバックでは再現しないため必ずLAN IPで）
for f in a.png b.png c.png d.png e.png f.png; do
  curl -s -o /dev/null -w "%{http_code} " -X POST http://<LAN-IP>:8996/api/upload -F "image=@$f"
done
# 期待: 200 200 200 200 200 200 （429 が出たら回帰）

# LAN からの管理操作は拒否されること
curl -s -X POST http://<LAN-IP>:8996/api/control -H "Content-Type: application/json" -d '{"action":"stop"}'
# 期待: 403 Forbidden
```

---

## 6. 検証時に踏んだ罠

1. **ブラウザは必ずハードリロード（Ctrl+Shift+R）**。リロード前のタブが旧UIのままで、誤ったFAIL判定が2回出ました。
2. **起動直後の約12秒は `/stream.m3u8` が404**。プレビュー関連を検証するときは、この窓の内か外かで結果が変わります。「配信が始まっている状態」だけで確認すると、404窓の不具合を見逃します（実際に見逃しました）。
3. **一括アップロードの不具合はループバックでは再現しません。** 必ずLAN IPで検証してください。
4. **テストでconfigが書き換わります。** `set_image_duration` などを叩くと `config.json` に永続化されます。検証後は元に戻すこと（配布側は `write_dist_config()` で再生成できます）。
5. **`hls_output/images/` は削除されなくなりました**（写真保持のため）。テストでアップロードした画像は手で消さないとスライドショーに混ざります。
6. **サブエージェントの報告を鵜呑みにしないこと。** `btnSkip` 二重POSTはソース確認で否定できました。一方で「モード選択の巻き戻し」「プレビュー開閉の復帰遅延」は正当な指摘で、こちらの修正の欠陥を突いています。**どちらもソースで裏を取ってから判断してください。**

---

## 7. 関連ファイル

| ファイル | 役割 |
|---|---|
| `ui/index.html` | **WebリモコンUIの正本**。ここだけを編集する |
| `plugin/ui/index.html` | ビルド時に `ui/index.html` から自動コピー。手で編集しない |
| `config.dist.json` | **配布用configの正本**。作業用 `config.json` とは別物 |
| `build_exe.py` | ビルド・パッケージング・`verify_release()` |
| `api_server.py` | HTTP API。`get_ui_html()` / `is_local_request()` / レートリミット |
| `streamer_core.py` | 配信コア。`play_radio()` / `play_image()` / `clean_hls_dir()` / スライドショー |
| `CHANGELOG.md` | v2.6.0 の修正内容を全て記載済み |
