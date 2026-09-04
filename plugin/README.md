# VRC_Media_Streamer Plugin for VRCBeacon

本フォルダ（`plugin/`）は、VRCBeaconのドロップインプラグインとして配布・配備するための資材パッケージです。

## 📁 フォルダ構成

```text
plugin/
├── plugin.json       # プラグイン定義メタデータ（ID、UI種別、起動バイナリ等）
├── README.md         # 本ドキュメント
├── ui/               # プラグインUI（WebUI / Vue / HTML / Tailwind）
└── bin/              # ヘッドレス動作用バイナリ（VRC_Media_Streamer.exe 等）
```

## 🚀 配布・導入手順

### 1. 配布パッケージ（ZIP）の作成
`plugin/` フォルダ配下の全ファイルを ZIP 圧縮して配布します。
```text
vrcbeacon-plugin-vrc-media-streamer-vX.X.X.zip
├── plugin.json
├── ui/
└── bin/
    └── VRC_Media_Streamer.exe (および依存ファイル)
```

### 2. VRCBeacon 側への配置
VRCBeacon のプラグインディレクトリ（`beacon/plugins/` 等）配下に本フォルダを展開します。
```text
VRCBeacon/
└── beacon/plugins/
    └── vrc-media-streamer/
        ├── plugin.json
        ├── ui/
        └── bin/
```

### 3. 開発時の連携（シンボリックリンク / ジャンクション）
開発時はファイルをコピーせず、ジャンクションを作成することで変更を即座に共有できます（※フォルダ名は `plugin.json` の `id` である `vrc-media-streamer` に一致させてください）。
```powershell
cmd /c mklink /J "E:\Projects\VRCBeacon\plugins\vrc-media-streamer" "E:\Projects\VRC_Media_Streamer\plugin"
```

## 📖 関連ドキュメント
- [VRCBeacon 橋渡し仕様・引継ぎ書](BEACON_BRIDGE_HANDOVER.md) (通信契約、セキュリティ検証、動作検証結果)

---

## 📌 VRCBeacon に埋め込むときの決まり（2026-09-04 追記）

**橋渡しの契約は `BEACON_BRIDGE_HANDOVER.md`。** UI の `fetch` や権限まわりを触る前に読むこと。
`hello` を受け取るまでは「Beacon の外」として直 `fetch` に落ちる作りで、その判定を変えると
ホスト権限が静かに落ちる。

**資材はオリジンのルートから引かないこと。** Beacon の中ではオリジンが
`beacon-plugin://vrc-media-streamer` になり、`/app-mark.png` は `api_server.py` ではなく
**このフォルダの直下**を指す。ルート絶対パスで引く資材は、このフォルダにも実体を置く必要がある。

- `plugin/app-mark.png` は `assets/app_mark.png` の写し。**写すのは `build_exe.py` の
  `sync_plugin_root_assets`**（`package_plugin` から呼ばれる）。対象を増やすときは
  そこの `PLUGIN_ROOT_ASSETS` に 1 行足すこと
- ずれと増加は `test_ui_assets.py` の 3 件が検知する（写しのバイト一致・ルート絶対パスの
  参照が増えていないこと・写さないと決めたものが明記されていること）
