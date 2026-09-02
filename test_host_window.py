# -*- coding: utf-8 -*-
"""モダンUI（WebViewホスト画面）の回帰テスト。

ホスト画面は `ui/index.html` を WebView2 で開いたもので、ネイティブ機能だけを
`window.pywebview.api` として橋渡ししている。ここで固定したいのは2点:

1. **js_api に状態を公開属性で持たない**こと。pywebview は js_api オブジェクトの
   公開属性を再帰的に walk するため、`self.window` のように持つと .NET オブジェクトを
   舐めて `maximum recursion depth exceeded` を吐き、StreamerCore のメソッドまで
   ページへ露出する（実際に発生させた）。
2. **WebView が使えない環境で例外にせず False を返す**こと。ここで落ちると
   「EXEを起動したのに何も出ない」になる。従来画面へ落ちれば操作は続けられる。
"""

import io
import os
import sys

import pytest

import host_window
from host_window import HostBridge

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_HTML = os.path.join(BASE_DIR, "ui", "index.html")

EXPECTED_API = {
    "host_info",
    "add_video_files",
    "add_photo_files",
    "select_standby_image",
    "reveal_video_url",
    "open_external",
    "exit_app",
}


class _FakeCore:
    def __init__(self):
        self.config = {"port": 8000}


def test_bridge_exposes_only_intended_methods():
    """公開されるのは意図した関数だけで、状態は一つも公開しないこと。"""
    bridge = HostBridge(_FakeCore(), object())
    public = {name for name in dir(bridge) if not name.startswith("_")}
    assert public == EXPECTED_API, f"公開APIが変わっている: {sorted(public)}"
    for name in public:
        assert callable(getattr(bridge, name)), (
            f"'{name}' が非callableで公開されている。pywebview がこの中身を"
            f"再帰的に走査してしまうため、内部参照は '_' 始まりにすること。"
        )


def test_run_host_window_returns_false_without_webview(monkeypatch):
    """pywebview が無い環境では例外を投げず False を返すこと（従来画面へ落とすため）。"""
    monkeypatch.setitem(sys.modules, "webview", None)
    assert host_window.run_host_window(_FakeCore(), object()) is False


def test_is_available_does_not_raise(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)
    assert host_window.is_available() is False


@pytest.mark.parametrize("element_id", [
    "hostFilePicker",        # PCから直接追加（容量無制限）
    "btnHostExit",           # アプリ終了
    "btnHostRevealUrl",      # ストリームキーの表示
    "hostSettingsCard",      # ホスト専用設定
    "hostPort",
    "hostEnableTunnel",
    "hostHlsSegment",
    "hostTransitionWait",
    "hostLiveSync",
    "hostStandbyMode",
    "hostStandbyImageRow",
    "hostLoopQueue",
    "hostShuffle",
    "hostAllowAdd",
    "hostAllowEdit",
    "hostAllowControl",
    "hostWebPassword",
])
def test_ui_has_host_elements(element_id):
    """ホスト画面に必要なUIが `ui/index.html` に存在すること。

    ホスト画面の正本はこのHTML一枚なので、ここが欠けると
    「デスクトップからは設定できない」機能が静かに生まれる。
    """
    with io.open(UI_HTML, encoding="utf-8") as f:
        html = f.read()
    assert f'id="{element_id}"' in html, f"ホストUI要素が無い: {element_id}"


def test_host_only_controls_are_hidden_by_default():
    """ネイティブ機能のUIは既定で hidden であること。

    ブラウザ（フレンドのスマホ）で開いたときに押せてしまうと、
    反応しないボタンが並ぶだけになる。表示は pywebviewready 後にJSが行う。
    """
    with io.open(UI_HTML, encoding="utf-8") as f:
        html = f.read()
    for element_id in ("hostFilePicker", "btnHostExit", "btnHostRevealUrl", "hostSettingsCard"):
        idx = html.index(f'id="{element_id}"')
        # 同じタグ内の class 属性を見る
        tag_start = html.rfind("<", 0, idx)
        tag_end = html.index(">", idx)
        tag = html[tag_start:tag_end]
        assert "hidden" in tag, f"{element_id} が既定で表示されている: {tag[:160]}"


def test_stream_key_is_masked_on_host_screen():
    """ホスト画面でストリームキーが既定でマスクされること。

    ストリームキーは実質パスワードで、画面共有や配信に映り込むと配信を乗っ取られる。
    従来のデスクトップ画面は既定でマスクしていたので、置き換えたホスト画面でも
    同じでなければ**セキュリティ上の退行**になる（実際に一度そうなった）。
    コピーは常に本物を渡すのも従来画面と同じ。
    """
    with io.open(UI_HTML, encoding="utf-8") as f:
        html = f.read()
    assert "function maskStreamUrlForDisplay" in html, "マスク関数が無い"
    assert "function displayStreamUrl" in html, "表示切替の関数が無い"
    # 表示は displayStreamUrl 経由であること（生の streamUrl を直接入れない）。
    # setMaskableUrlValue が「表示はマスク / dataset.realValue に本物」を一手に引き受ける。
    assert "function setMaskableUrlValue" in html, "表示と実値を分ける関数が無い"
    assert "el.value = real ? displayStreamUrl(real)" in html, "表示がマスクを通っていない"
    assert "setMaskableUrlValue(quickUrl, streamUrl" in html, "クイックバーがマスクを通っていない"
    assert "setMaskableUrlValue(infoStream, streamUrl)" in html, "接続タブがマスクを通っていない"
    assert "setMaskableUrlValue(destUrlEl, destUrl)" in html, "配信先URL欄がマスクを通っていない"
    # コピーは本物。value（＝伏字）ではなく dataset.realValue を先に見ること。
    assert "const url = realStreamUrl || document.getElementById('quickStreamUrl').value;" in html,         "コピーがマスク表示値を掴んでいる"
    assert "const val = (el.dataset && el.dataset.realValue) || el.value;" in html,         "コピーボタンが伏字のまま貼り付けている"
    # 鍵を持たない HLS URL まで潰さないこと
    assert "^rtmps?:|^rtsp[st]?:" in html, "マスク対象が RTMP/RTSP に限定されていない"


def test_gui_falls_back_to_classic_ui():
    """gui_streamer 側に「WebViewがダメなら従来画面」の分岐が残っていること。"""
    with io.open(os.path.join(BASE_DIR, "gui_streamer.py"), encoding="utf-8") as f:
        src = f.read()
    assert "run_host_window" in src, "モダンUIの起動経路が無い"
    assert "--classic-ui" in src, "従来画面へ明示的に戻す手段が無い"
    assert "app = App(core, server)" in src, "従来画面へのフォールバックが無い"
