# VRCYouTube Plugin for VRCBeacon

本フォルダ（`plugin/`）は、VRCBeaconのドロップインプラグインとして配布・配備するための資材パッケージです。

## 📁 フォルダ構成

```text
plugin/
├── plugin.json       # プラグイン定義メタデータ（ID、UI種別、起動バイナリ等）
├── README.md         # 本ドキュメント
├── ui/               # プラグインUI（WebUI / Vue / HTML / Tailwind）
└── bin/              # ヘッドレス動作用バイナリ（VRCYouTubeStreamer.exe 等）
```

## 🚀 配布・導入手順

### 1. 配布パッケージ（ZIP）の作成
`plugin/` フォルダ配下の全ファイルを ZIP 圧縮して配布します。
```text
vrcbeacon-plugin-vrcyoutube-vX.X.X.zip
├── plugin.json
├── ui/
└── bin/
    └── VRCYouTubeStreamer.exe (および依存ファイル)
```

### 2. VRCBeacon 側への配置
VRCBeacon のプラグインディレクトリ（`beacon/plugins/` 等）配下に本フォルダを展開します。
```text
VRCBeacon/
└── beacon/plugins/
    └── vrcyoutube/
        ├── plugin.json
        ├── ui/
        └── bin/
```

### 3. 開発時の連携（シンボリックリンク / ジャンクション）
開発時はファイルをコピーせず、ジャンクションを作成することで変更を即座に共有できます（※フォルダ名は `plugin.json` の `id` である `vrcyoutube-streamer` に一致させてください）。
```powershell
cmd /c mklink /J "E:\Projects\VRCBeacon\plugins\vrcyoutube-streamer" "E:\Projects\VRCYouTube\plugin"
```

## 📖 関連ドキュメント
- [VRCBeacon 橋渡し仕様・引継ぎ書](BEACON_BRIDGE_HANDOVER.md) (通信契約、セキュリティ検証、動作検証結果)

