# -*- coding: utf-8 -*-
"""Webリモコン（ゲスト）に見せる範囲の回帰テスト。

ホスト画面とWebリモコンは同じ `ui/index.html` を使い回している。そのため
「ホストにしか意味がない画面」をゲストへ出す事故が起きやすい。ここで固定するのは3点:

1. **「配信・QR設定」タブはホストPC専用**。配信先URL・ストリームキー・
   Webリモコンのパスワード・権限設定がそのまま並ぶ画面で、ゲストに渡ると
   配信を乗っ取られる。
2. **「接続 & スマホ共有」タブは既定で非表示**。中身はPIN付きのリモコンURLと
   共有QRなので、渡した相手がさらに第三者へ配れてしまう。ホストが
   `allow_web_share_info` を明示的に立てたときだけ見せる（fail-closed）。
3. **サーバー側でも塞ぐ**。UIで隠しただけでは `/api/qrcode` の直叩きが残る。
"""

import io
import os

import pytest

import api_server
import streamer_core

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_HTML = os.path.join(BASE_DIR, "ui", "index.html")


def _ui():
    with io.open(UI_HTML, encoding="utf-8") as f:
        return f.read()


def test_share_info_is_denied_by_default():
    """許可設定は fail-closed（既定 False）であること。"""
    assert streamer_core.DEFAULT_CONFIG["allow_web_share_info"] is False


def test_status_exposes_share_info_permission():
    """UIが判断に使う許可フラグが /api/status に載ること。

    載っていないとUI側は「未指定＝非許可」に倒れるため画面は安全側だが、
    ホストが許可しても反映されない（＝機能が死ぬ）。
    """
    core = streamer_core.StreamerCore()
    perms = core.get_status_data()["permissions"]
    assert perms["allow_web_share_info"] is False

    core.config["allow_web_share_info"] = True
    perms = core.get_status_data()["permissions"]
    assert perms["allow_web_share_info"] is True


class _FakeCore:
    def __init__(self, allow):
        self.config = {"allow_web_share_info": allow}


def _handler(is_local, allow):
    """ソケットを張らずに判定メソッドだけを試すための最小の器。"""
    h = object.__new__(api_server.APIAndHLSHandler)
    h.streamer_core = _FakeCore(allow)
    h.is_local_request = lambda: is_local
    return h


@pytest.mark.parametrize("is_local,allow,expected", [
    (True, False, True),    # ホストPCは許可設定に関わらず常に見える
    (True, True, True),
    (False, False, False),  # ゲストは既定で見えない
    (False, True, True),    # ホストが明示的に許可したときだけ見える
])
def test_may_see_share_info(is_local, allow, expected):
    assert _handler(is_local, allow).may_see_share_info() is expected


def test_qrcode_endpoint_consults_the_permission():
    """/api/qrcode がUIの表示制御と同じ判定を通ること（直叩き対策）。"""
    with io.open(os.path.join(BASE_DIR, "api_server.py"), encoding="utf-8") as f:
        src = f.read()
    head, _, tail = src.partition('elif path == "/api/qrcode":')
    assert tail, "/api/qrcode のハンドラが見当たらない"
    # QR画像を作り始める前に判定していること
    guard = tail.index("may_see_share_info")
    generate = tail.index("qr.add_data")
    assert guard < generate, "QRを生成した後で判定している（生成前に塞ぐこと）"


def test_ui_hides_host_only_tabs_from_guests():
    html = _ui()
    assert "function applyRemoteTabVisibility" in html, "タブ可視性の制御が無い"
    # 「配信・QR設定」はホスト限定、「接続 & スマホ共有」は許可があるときだけ
    assert "const showSettings = isHost;" in html, "設定タブがホスト限定になっていない"
    assert "const showInfo = isHost || guestCanSeeShareInfo;" in html,         "共有タブが許可フラグを見ていない"
    assert "navSettings.classList.toggle('hidden', !showSettings)" in html
    assert "navInfo.classList.toggle('hidden', !showInfo)" in html
    # プレイヤータブの「QR共有」ボタンも同じ扱い（隠したタブへの入口を残さない）
    assert 'id="btnGoShareQr"' in html, "QR共有ボタンにidが無く連動して隠せない"
    assert "btnShareQr.classList.toggle('hidden', !showInfo)" in html


def test_ui_defaults_to_denied_when_permission_is_absent():
    """許可フラグが来ていないとき（古いサーバー・オフライン）は非表示に倒すこと。"""
    html = _ui()
    assert "guestCanSeeShareInfo = !!(data.permissions && data.permissions.allow_web_share_info === true);" in html,         "未指定を許可扱いにしている"
    # オフライン時は前回値を引きずらない
    head, _, tail = html.partition("function updateUiOffline()")
    assert tail, "updateUiOffline が見当たらない"
    assert "guestCanSeeShareInfo = false;" in tail[:2000], "オフライン時に許可を落としていない"


def test_switch_tab_refuses_hidden_tabs():
    """onclick を直接叩かれても隠したタブを開かせないこと。"""
    html = _ui()
    head, _, tail = html.partition("function switchTab(tabId)")
    assert tail, "switchTab が見当たらない"
    body = tail[:800]
    assert "nav.classList.contains('hidden')" in body, "隠れたタブへの遷移を弾いていない"
    assert "tabId = 'player';" in body, "弾いた後の行き先が無い"


def test_host_can_grant_share_info_from_the_settings_screen():
    """許可を切り替える手段が両方の設定画面にあること。

    フラグを足しただけで切り替えるUIが無いと、既定 False は
    「機能が消えた」としか見えない。
    """
    html = _ui()
    assert 'id="hostAllowShareInfo"' in html, "ホスト設定画面にトグルが無い"
    assert "set('hostAllowShareInfo', cfg.allow_web_share_info);" in html, "読み込みが無い"
    assert "allow_web_share_info: bool('hostAllowShareInfo')," in html, "保存が無い"

    with io.open(os.path.join(BASE_DIR, "gui_streamer.py"), encoding="utf-8") as f:
        gui = f.read()
    assert "switch_web_share_info" in gui, "従来設定画面にトグルが無い"
    assert '"allow_web_share_info": bool(self.switch_web_share_info.get()),' in gui,         "従来設定画面が保存していない"
