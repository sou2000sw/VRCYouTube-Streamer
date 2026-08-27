# VRCBeacon との橋渡し —— 引継ぎ書

> [!IMPORTANT] これは写し。原本は VRCBeacon 側にある
> 原本: `E:\Projects\VRCBeacon\Beacon\docs\09-plugin-bridge-handover.md`
>
> 契約（`hello` / `request` / `response` の形、制約）を決めているのは **VRCBeacon 側**。
> 契約が変わったら**両方を直すこと。片方だけ直さない。**
> 実装の進捗や、この repo だけの判断は、こちら側に書き足してよい。

**作業先はこの repo（`E:\Projects\VRCYouTube`）。VRCBeacon のコードは変えない。**
VRCBeacon 側の受付口（`src-electron/plugins/`）と画面（`src/views/Beacon/BeaconPluginHost.vue`）は
2026-08-25 に実装・コミット済み（`7430dc04` / `028877b5`）。
受付口の仕様は `E:\Projects\VRCBeacon\Beacon\docs\08-plugin-loader-spec.md`。

やることは 1 つ。**`plugin/ui/index.html` の `fetch` を、Beacon の中にいるときだけ
`postMessage` 経由へ差し替える層を足す。** 既存の呼び出し 14 箇所は書き換えない。

---

## 1. なぜ要るのか —— 直 `fetch` のままだと何が起きるか

`ui/index.html`（この repo の `plugin/ui/index.html`）は現状 `postMessage` を **1 箇所も使っておらず**、
`fetch(`${apiBase}/api/...`)` で `http://127.0.0.1:8000` を直接叩く
（`apiBase` は 437 行目、`localStorage` の `vrc_media_streamer_api_base` 既定 `http://127.0.0.1:8000`）。

Beacon の中では iframe のオリジンが **`beacon-plugin://vrc-media-streamer`** になる。
`../api_server.py` の `is_local_request()` は「ループバックの IP」かつ「`_origin_is_self()`」を
要求し、`_origin_is_self()` は **Origin が無いとき True**、あるときは `_self_origins()`
（`http://127.0.0.1:8000` 等）に含まれることを要求する。**`beacon-plugin://` は含まれない。**

結果、Beacon に埋め込んだ操作パネルが**ホスト本人の操作ではなく「Web からの遠隔操作」として
扱われる**。既定設定での実際の挙動:

| 呼び先 | 直 `fetch` の結果 | 根拠 |
|---|---|---|
| `GET /api/status` | 通る | 権限判定なし |
| `GET /api/config` | **常に 403** | `api_server.py:1079` |
| `POST /api/config` | **常に 403** | `api_server.py:1394` |
| `POST /api/shutdown` | **常に 403** | `api_server.py:1409` |
| control `clear_queue` / `stop` | **常に 403** | `api_server.py:1289` |
| control `delete_item` / `move_item` | `allow_web_queue_edit` 次第（既定 True） | `api_server.py:1297` |
| control `skip` / `prev` / `set_loop` ほか | `allow_web_playback_control` 次第（既定 True） | `api_server.py:1306` |
| `POST /api/queue` | `allow_web_queue_add` 次第（既定 True）＋レート制限 | `api_server.py:1238` |
| `POST /api/upload` | 同上 | `api_server.py:1156` |

CORS は通る（`Access-Control-Allow-Origin: *`、`api_server.py:1042`）。
混在コンテンツにもならない（`http://127.0.0.1` は Chromium が信頼できる出所として扱う）。
**問題は権限の降格だけ。**

### 見落としやすい影響

既定のままなら「設定と停止が使えない」程度に見える。だが**ホストが Web リモコンを絞ると、
Beacon の中のパネルも一緒に死ぬ**。`allow_web_playback_control` を切れば、
手元の Beacon から `skip` すら押せなくなる。

「配信を他人に触らせない」という正しい設定が、**自分の手元の操作パネルを壊す**。
この食い違いが直 `fetch` のままにできない理由で、`/api/config` が 403 になることより重い。

橋渡しを通せば、呼び出しは Electron のメインプロセスから出て **Origin が付かない**ので、
`is_local_request()` が True になりホスト本人の操作として扱われる。
2026-08-25 の実測で `/api/config` が 200 で返ることを確認済み（VRCBeacon 側の `08-plugin-loader-spec.md`）。

---

## 2. 契約 —— Beacon 側が既に用意しているもの

`BeaconPluginHost.vue` が `window.addEventListener('message', ...)` で待っている。

### 2-1. Beacon → プラグイン（読み込み完了時に 1 回）

```js
{ __beaconPlugin: 'hello', id: 'vrc-media-streamer', version: '2.5.0',
  allowedOrigins: ['http://127.0.0.1:8000'] }
```

**これが来なければ Beacon の外**（ブラウザで直接開かれた、Web リモコン等）。
そのときは今までどおり直 `fetch` で動かすこと。**`hello` の有無が唯一の判定材料**で、
`window.parent !== window` で判定してはいけない（別の何かに埋め込まれている場合と区別できない）。

### 2-2. プラグイン → Beacon（呼び出し）

```js
parent.postMessage({
    __beaconPlugin: 'request',
    requestId,          // 任意の一意な値。応答の突き合わせに使う
    url,                // 絶対 URL。permissions の許可リスト内であること
    method,             // GET / POST / PUT / PATCH / DELETE
    headers,            // accept と content-type だけ通る。他は捨てられる
    body                // 文字列、または Uint8Array / ArrayBuffer（上限 20MB。後述の 4）
}, 'beacon-plugin://vrc-media-streamer');
```

### 2-3. Beacon → プラグイン（応答）

```js
{ __beaconPlugin: 'response', requestId,
  ok: true,  status: 200, contentType: 'application/json; charset=utf-8', body: '{...}' }
// または
{ __beaconPlugin: 'response', requestId, ok: false, reason: '許可リストに無い宛先です: ...' }
```

`ok` は **中継できたか**であって HTTP の成否ではない。403 も 404 も `ok: true` で
`status` に載って返る。`ok: false` は関門で止められたか、通信そのものが失敗した場合。

### 2-4. 制約（`src-electron/plugins/index.js`）

- 宛先は `plugin.json` の `permissions` の範囲内、かつ**ループバックのみ**。外部ホストは通らない
- ヘッダは `accept` と `content-type` のみ。`Origin` / `Cookie` / `Authorization` は差し込めない
- リダイレクトは追わない（`redirect: 'error'`）
- 応答は **4MB** 上限、**15 秒**でタイムアウト
- **応答本文は UTF-8 の文字列として返る。** 画像などのバイナリは壊れる（今の UI は
  API から画像を受け取っていないので影響なし。`/api/qrcode` を使うなら 4 を読むこと）
- 返信は `event.source` で差出人を確認したうえで名指しで返る。`'*'` では受け取れない

---

## 3. 実装の形（30 行程度）

`ui/index.html` の `apiBase` を定義している **437 行目の直後**に置くのが素直。
既存の `fetch(...)` は 1 箇所も書き換えない。

```js
// Beacon の中にいるときだけ、apiBase 宛ての fetch を主プロセス経由へ回す。
// 直で叩くと Origin が付き、ホスト本人の操作ではなく Web からの遠隔操作として
// 扱われる（設定の取得・停止・全消去が 403、ホストが Web 操作を切ると再生操作も死ぬ）。
(function () {
    let beacon = null;                 // hello が来るまで null = Beacon の外
    const pending = new Map();
    let seq = 0;

    window.addEventListener('message', (event) => {
        const m = event.data;
        if (!m || typeof m !== 'object') return;
        if (m.__beaconPlugin === 'hello') { beacon = { origin: event.origin, id: m.id }; return; }
        if (m.__beaconPlugin === 'response') {
            const resolve = pending.get(m.requestId);
            if (resolve) { pending.delete(m.requestId); resolve(m); }
        }
    });

    const nativeFetch = window.fetch.bind(window);

    window.fetch = function (input, init = {}) {
        const url = typeof input === 'string' ? input : input?.url;
        // Beacon の外、apiBase 以外、運べない本文は、今までどおり直で。
        // 運べるのは文字列とバイト列（Uint8Array / ArrayBuffer）。FormData は運べないので、
        // /api/upload はプラグイン側で multipart のバイト列を組んでから渡すこと（4 を読む）。
        const bodyOk = init.body == null || typeof init.body === 'string' ||
            ArrayBuffer.isView(init.body) || init.body instanceof ArrayBuffer;
        if (!beacon || typeof url !== 'string' || !url.startsWith(apiBase) || !bodyOk) {
            return nativeFetch(input, init);
        }

        const requestId = `r${++seq}`;
        return new Promise((resolve, reject) => {
            pending.set(requestId, (m) => {
                if (!m.ok) { reject(new Error(m.reason || 'plugin bridge refused')); return; }
                // 既存の呼び出しは res.ok / res.status / res.json() を見ているので、
                // Response で包んで返す —— 呼び出し側を 1 行も変えないため。
                resolve(new Response(m.body, {
                    status: m.status,
                    headers: m.contentType ? { 'content-type': m.contentType } : {}
                }));
            });
            parent.postMessage({
                __beaconPlugin: 'request', requestId, url,
                method: init.method || 'GET',
                headers: init.headers || {},
                body: init.body ?? undefined
            }, beacon.origin);
        });
    };
})();
```

**`Response` で包んで返すのが要点。** 既存の 14 箇所は `res.ok` / `res.status` / `res.json()`
を見ているので、そこを 1 行も触らずに差し替えられる。

### タイムアウトの扱い

Beacon 側が 15 秒で打ち切って `ok: false` を返すので、`pending` は必ず解決される。
ただし**プラグインが Beacon 以外の何かから偽の `response` を受け取らないよう**、
`event.origin === beacon.origin` の確認を足しておくと堅い（上の雛形は `hello` の
origin を覚えているだけなので、そこまで書くこと）。

---

## 4. `/api/upload` —— 案 B。Beacon 側は対応済み、この repo が残り

`ui/index.html` 810 行目の画像アップロードは **`FormData` に `File` を入れて投げている**。
`FormData` は `postMessage` で運べないので、**この 1 箇所だけはこの repo の書き換えが要る**
（他の 13 箇所は雛形のままで乗る）。運ぶ形は **multipart のバイト列**。

### 【2026-08-25 実測】「困ったら」ではなく、既に壊れている

`allow_web_queue_add`（既定 true）とは**別の関門**がある。`api_server.py:1164` の
`check_rate_limit()` は、**非ローカル扱いの相手を IP あたり 2.5 秒に 1 回**に絞る
（`QUEUE_RATE_LIMIT_SECONDS = 2.5`）。実測:

```
■ Origin あり（今の iframe からの直 fetch と同じ条件）
  1 枚目: 200 Successfully uploaded photo: 🖼 photo_1
  2 枚目: 429 Rate limit exceeded...
  3 枚目: 429 Rate limit exceeded...
  4 枚目: 429 Rate limit exceeded...
■ Origin なし（橋渡し = 主プロセス経由と同じ条件）
  1〜4 枚目: すべて 200
```

`handleImageFiles()` は選ばれたファイルを**間を空けずにループ**して投げるので、
10 枚選んでも通るのは 1 枚。しかも数え方が `if (res.ok) successCount++;` なので、
**429 は例外にならず、エラーも出さずに「1 枚追加しました」と表示される。9 枚が黙って消える。**

Web リモコン向けの連投防止としては正しい仕様。問題は、**Beacon に埋め込んだパネルまで
「Web からの他人」として数えられている**こと —— 1 の「見落としやすい影響」と同じ構図が、
**既定設定のまま既に起きている**。

### 案 B —— 当初の想定よりずっと簡単だった

`api_server.py:1191` は **multipart 以外の生ボディも受け付ける**（実測で 200 を確認）:

```python
if "multipart/form-data" in content_type:
    img_bytes, filename = parse_multipart_file(body_bytes, content_type)
else:
    img_bytes = body_bytes
    filename = "uploaded_image.png"
```

つまり橋渡し側に **multipart の組み立ては要らない**。そして **base64 も要らない** ——
`postMessage` も Electron の IPC も structured clone なので、`Uint8Array` をそのまま運べる
（base64 の 33% 膨張を避けられる）。必要な変更は VRCBeacon 側の 1 箇所だけ:

```javascript
// src-electron/plugins/index.js の proxyRequest
// 今: 文字列以外を拒否
if (typeof body !== 'undefined' && body !== null && typeof body !== 'string') {
    return { ok: false, reason: '本文は文字列で渡してください' };
}
// → Uint8Array / ArrayBuffer も受ける。許可リストの検査は一切変わらない
```

### 【2026-08-25 対応済み】Beacon 側

`normalizeRequestBody()` が入り、`proxyRequest` の本文は **文字列 / `Uint8Array` /
`ArrayBuffer`** の 3 つで受ける。上限は `MAX_REQUEST_BODY_BYTES = 20MB`
（応答側の 4MB とは別方向の値なので分けてある）。
**許可リスト・メソッド・ヘッダの検査は 1 行も変わっていない。**

この repo から見て効いてくるのは 3 点:

- `Uint8Array` を渡せば**そのまま**運ばれる。base64 に包む必要は無い
- **切り出した `Uint8Array`（`subarray` 等）は、その範囲だけが送られる**
- 20MB を超える本文は Beacon 側で `ok: false` になる（相手へ届く前に落ちる）

### 残り —— この repo

`handleImageFiles()` の `FormData` を、**multipart のバイト列を自前で組む**形へ。
生ボディでも 200 は返るが、**題名が全部 `🖼 uploaded_image` になる**（実測）ので組む方を採る。
`successCount` の数え方（`if (res.ok)`）も、橋渡しの外（Web リモコン）では
429 を黙って飲み込むままなので、あわせて見ておくとよい。

**題名を残したい場合だけ**、プラグイン側で multipart のバイト列を組み立てて `Uint8Array` で渡す。
生ボディだと**全部の題名が `🖼 uploaded_image` になる**（実測で確認）。
サーバー側の上限は 20MB（`MAX_UPLOAD_BODY_BYTES`）で、`plugin:request` 側もそこへ合わせてある。

### 3 案の比較（実測後）

| 案 | 実際どうなるか |
|---|---|
| A（現状） | **複数枚選択が既に壊れている**（1 枚だけ、しかも黙って落ちる）。ホストが `allow_web_queue_add` を切ると 403 で全滅 |
| **B（推奨）** | VRCBeacon 側の 1 箇所で `body` の型を広げるだけ。multipart 解析も base64 も不要。レートリミットも 403 も回避され、題名も保てる |
| C | **採らない。** Origin の名乗りだけで本人権限を渡すことになり、`_origin_is_self()` を置いた意味が消える |

**当初は「A で始めて、困ったら B」と書いていたが、実測を踏まえて B を推奨に変えた。**
「困ったら」の状態に既に入っており、しかも B のコストが想定よりはるかに小さいため。

---

## 5. 検証のしかた

**完了報告ではなく成果物で確かめること。**

1. ジャンクションを貼る（フォルダ名は `plugin.json` の `id` に合わせる。
   `vrc_media_streamer` にすると「フォルダ名と id が一致しません」の警告が出る）
   ```
   cmd /c mklink /J "E:\Projects\VRCBeacon\plugins\vrc-media-streamer" "E:\Projects\VRCYouTube\plugin"
   ```
2. VRCBeacon を起動 → ナビの「プラグイン」→ 管理タブでスイッチを入れる
3. プラグインのタブが増えるので開く
4. **`GET /api/config` が 200 で返ることを確認する。** ここが 403 なら橋渡しが効いていない
   （直 `fetch` に落ちている）。DevTools の Network に `127.0.0.1:8000` への要求が
   **出ていないこと**でも判別できる —— 橋を通っていれば主プロセスから出るので、
   レンダラーの Network には現れない
5. ブラウザで `http://127.0.0.1:8000` を直接開き、**今までどおり動くこと**を確認する
   （`hello` が来ないので直 `fetch` のまま。ここが壊れたら Web リモコンを壊したことになる）

---

## 6. VRCBeacon 側を変える必要が出る条件

以下に当たったら、VRC_Media_Streamer 側で回避せず VRCBeacon 側へ戻すこと。

- バイナリの送受信が要る（上の 4-B、`/api/qrcode` を UI に出す等）
- 応答が 4MB を超える、または 15 秒で終わらない
- `accept` / `content-type` 以外のヘッダが要る
- ループバック以外の宛先が要る → **これは通さない。** 外部へ出るものは
  `PayloadGate` を通す必要があり、プラグインの中継はその外にある

---

# 【2026-08-25】現在地 —— 実装され、通し確認まで済んだ

以下は**この引継ぎ書を書いたあとに起きたこと**。上の 1〜6 は契約の説明として有効なまま。

## 何が終わっているか

| 場所 | 状態 |
|---|---|
| VRCBeacon 受付口 `src-electron/plugins/` | 実装・コミット済み（`7430dc04`）。vitest 61 件 |
| VRCBeacon 画面 `src/views/Beacon/BeaconPlugin*.vue` | 実装・コミット済み（`028877b5`）。vitest 9 件 |
| VRC_Media_Streamer 橋渡し `plugin/ui/index.html` | **実装済み・未コミット**（`master` に 73 行の追加のみ、削除ゼロ） |

橋渡しは 3 の雛形どおりで、加えて **`response` の `event.origin` 確認**と
**ヘッダの正規化**（`Headers` インスタンス／配列／オブジェクトの 3 形態）が入っている。

## 通し確認の結果（実物の exe まで）

プラグイン側の橋渡しと VRCBeacon 側の `proxyRequest` を繋ぎ、実物の
`VRC_Media_Streamer.exe` を起動して叩いた。

```
GET  /api/status          -> ok=true 200
GET  /api/config          -> ok=true 200   ← 直 fetch なら 403 だった箇所
POST /api/control (skip)  -> ok=true 200   {"success":true,...}
終了後の残存プロセス: 0
```

**`/api/config` が 200。** 1 に書いた権限降格の問題は解消している。
呼び出し側を 1 行も変えずに `res.ok` / `res.status` / `res.json()` が動くことも確認済み。

橋渡し単体でも確認済み: `hello` 前は `postMessage` を 1 度も出さない（Web リモコンを壊さない）、
`hello` 後は中継へ回る、`FormData` は直 `fetch` に落ちる（4 の案 A）、
別オリジンからの偽 `response` は無視する。

---

# 次にやること

## 1. 【対応済み 2026-08-25】`hello` の差出人を確認していなかった

`response` 側には `event.origin` の確認があるが、**`beacon.origin` を決める `hello` 側に無い**。
そのため**先に偽の `hello` を送った者が `beacon.origin` になれる**。再現済み:

```
偽 hello（https://attacker.example.com）→ 乗っ取られた
  攻撃者へ渡った本文: {"url":"https://youtu.be/secret"}
  偽の応答が UI へ  : {"status":"偽の応答"}
```

以降の API 呼び出しが全て攻撃者へ流れ、応答も捏造される（`response` の確認は
`beacon.origin` と比べるだけなので素通りする）。

**現時点では到達経路が無い。** `plugin/ui/index.html` は Web サーバーから配信されておらず
（サーバーが返すのは別物の `HTML_PLAYER_TEMPLATE`）、`beacon-plugin://` の枠へ
`postMessage` できるのは Beacon のレンダラーだけ。**今すぐ悪用される状態ではない。**

それでも直す理由は、**この橋渡し自身が「Beacon の外で開かれる場合」の分岐を持っている**こと。
開発中にブラウザで開く、この HTML を Web リモコンへ流用する —— そのどちらかが起きた瞬間に
有効になる。サーバーは `X-Frame-Options` も `frame-ancestors` も送っていないので埋め込める。

> [!CAUTION] 2026-08-25 訂正 —— 最初に書いた案は間違っていた
> `event.origin.startsWith('beacon-plugin://')` と書いていたが、**これでは本物の `hello` も落ちる。**
> `event.origin` は**送り手**のオリジン。`hello` を送るのは Beacon のレンダラーで、
> そこは `mainWindow.loadFile(...)`（`src-electron/main.js:328`）で読み込まれるため **`file://`**。
> `postMessage(msg, 'beacon-plugin://<id>')` の第 2 引数は *targetOrigin*（受け手の制限）であって
> 送り手の名前ではないので、`event.origin` が `beacon-plugin://` になることは無い。
>
> 実測（偽の window で橋渡しの IIFE を動かした）:
> ```
> 本物の hello（source=window.parent, origin='file://'）-> 拒否された
> デバッグ起動（origin='http://localhost:9000'）        -> 拒否された
> origin='beacon-plugin://...'（実際には来ない形）      -> 受け入れた
> ```
> この案を入れると**橋渡しが一切効かず**、全て直 `fetch` に落ちて `/api/config` が 403 に戻る。
> **修正前より悪い。**

見るべきは送り手のオリジンではなく、**この頁自身がどこから配られたか**。

```javascript
if (m.__beaconPlugin === 'hello') {
    // beacon-plugin: は Electron の中にしか存在しないスキーム。この頁がそこから
    // 配られている事実そのものが「Beacon の中にいる」証拠になる。ブラウザで開かれた
    // 頁が悪意ある親に埋め込まれた場合は http/https なので、ここで落ちる。
    // event.origin を見てはいけない —— あれは送り手（Beacon のレンダラー = file://）の
    // オリジンで、beacon-plugin:// とは一致しない。
    if (location.protocol !== 'beacon-plugin:') return;
    if (event.source !== window.parent || window.parent === window) return;
    beacon = { origin: event.origin, id: m.id };
    return;
}
```

2-1 に「`window.parent !== window` で判定してはいけない」と書いたのは**単独の判定に使う場合**。
`location.protocol` の確認と組み合わせるのは問題ない。

### 【要実機確認】返信の targetOrigin

Chromium が `file://` のオリジンを `'file://'` と綴るか `'null'`（opaque）と綴るかで、
`parent.postMessage(msg, beacon.origin)` が `SyntaxError` になり得る（`'null'` は
targetOrigin に使えない）。**ここは推測せず、実機で確かめること。** 両方で動く形:

```javascript
// ここへ来る時点で location.protocol と window.parent は確認済みなので、
// '*' へ落としても届く先は Beacon のレンダラーだけ。
const replyTarget = beacon.origin && beacon.origin !== 'null' ? beacon.origin : '*';
```

`response` 側の `event.origin !== beacon.origin` の比較は、どちらの綴りでも
両側が同じ値を見るのでそのままでよい。

### 対応済み —— 実条件で確認した

`location.protocol !== 'beacon-plugin:'` と `event.source !== window.parent` の 2 段、および
`replyTarget` の落とし込みが `plugin/ui/index.html` に入った（**未コミット**）。
偽の `window` に本物と同じ条件を与えて全経路を確認:

| 条件 | 期待 | 結果 |
|---|---|---|
| 本物（`beacon-plugin:` / source=parent / origin=`file://`） | 通す | 通した |
| デバッグ起動（origin=`http://localhost:9000`） | 通す | 通した |
| opaque なオリジン（origin=`null`） | 通す | 通した |
| 攻撃: `https:` の頁が悪意ある親に埋め込まれた | 落とす | 落とした |
| 攻撃: `http:` の頁（Web リモコン流用） | 落とす | 落とした |
| 攻撃: 親ではない別の枠から（source≠parent） | 落とす | 落とした |

`targetOrigin` も、通常は `"file://"`、opaque のときだけ `"*"` へ落ちることを確認。

実物の exe まで通す統合確認もやり直し、**`/api/config` が 200**、
`POST /api/control (skip)` が 200、終了後の残存プロセス 0。

## 2. 【対応中・案 B】`/api/upload` の扱い

4 を読むこと。**A（現状）は既に壊れている** —— レートリミット（2.5 秒 / IP）により
複数枚選択で 1 枚しか入らず、しかも UI がエラーを出さないので黙って消える（実測済み）。

**Beacon 側は 2026-08-25 に対応済み**（`proxyRequest` が `Uint8Array` / `ArrayBuffer` を受ける。
上限 20MB）。**残りはこの repo** —— `handleImageFiles()` の `FormData` を multipart の
バイト列に組み替え、雛形の除外条件を「バイト列も通す」形にする。**C は採らない。**

## 3. 【未決定】VRC_Media_Streamer 側のコミット方針

`master` に直接コミットするか、ブランチを切るか。未決。

## 4. 【未実施】Electron を通した確認

ここまでの確認は全て **Electron を挟まずに**行っている（受付口のモジュールと橋渡しの
IIFE を直接動かした）。**まだ一度も本物のアプリで動かしていない。** 残っているのは:

- `beacon-plugin://` の実配信（`protocol.handle` 経由でファイルが返るか）
- 画面（ナビの「プラグイン」→ 管理タブ → スイッチ → プラグインのタブが増える）
- `postMessage` の実際の往復（上の確認は偽の `window`/`parent` で行った）
- `before-quit` の実発火（子プロセスが本当に片付くか）

手順は 5 のとおり。**フォルダ名は `vrc-media-streamer`**（`plugin.json` の `id`）にすること。

## 5. 【任意】`plugin/README.md` への 1 行

この引継ぎ書へのポインタ。README に載せないと、この repo で作業するセッションが
`BEACON_BRIDGE_HANDOVER.md` に気付かない。未実施。
