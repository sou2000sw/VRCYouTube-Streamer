# -*- coding: utf-8 -*-
"""初回起動時の既定値と、セットアップ案内の回帰テスト。

配布物の既定値は `config.dist.json` が正本で、`DEFAULT_CONFIG` は
「設定ファイルにキーが無かったときの受け皿」でしかない。両方を見ないと
「DEFAULT_CONFIG を直したのに配布物では効かない」という食い違いが起きる
（実際に radio_bg_source がその状態だった）。
"""

import io
import json
import os

import pytest

import streamer_core

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_HTML = os.path.join(BASE_DIR, "ui", "index.html")
DIST_CONFIG = os.path.join(BASE_DIR, "config.dist.json")


@pytest.fixture(scope="module")
def dist_config():
    with io.open(DIST_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def _ui():
    with io.open(UI_HTML, encoding="utf-8") as f:
        return f.read()


# --- 初回起動時の既定値 -------------------------------------------------

def test_default_destination_is_topaz(dist_config):
    """配信経路の既定は TopazChat（低遅延）。"""
    assert dist_config["output_mode"] == "topaz"
    assert streamer_core.DEFAULT_CONFIG["output_mode"] == "topaz"


def test_default_radio_background_is_thumbnail_card(dist_config):
    """ラジオモードの画面はサムネイルカード。

    'card' が UI の「🎵 サムネイルカード」に対応する値。写真プールが空でも
    必ず絵が出るので、初回起動の既定として 'slideshow' より妥当。
    """
    assert dist_config["radio_bg_source"] == "card"
    assert streamer_core.DEFAULT_CONFIG["radio_bg_source"] == "card"
    # UI 側に選択肢として存在し、コアも受け付けること
    assert '<option value="card">' in _ui()
    core = streamer_core.StreamerCore()
    assert core.set_radio_bg_source("card") == "card"


def test_bare_exe_launch_matches_normal_batch(dist_config):
    """EXEを素で起動したとき、Normalバッチ（--tunnel）と同じ状態になること。

    Normalバッチは `VRC_Media_Streamer.exe --tunnel` だけを渡す。素の起動が
    これと一致するには、配布 config の enable_tunnel が true である必要がある。
    ここが false だと「バッチ経由でしかトンネルが張られない」ことになり、
    exe を直接ダブルクリックした利用者だけ外部から繋がらない。
    """
    assert dist_config["enable_tunnel"] is True
    # Normalバッチが --tunnel 以外を渡していないこと（渡し始めたらこの前提が崩れる）
    with io.open(os.path.join(BASE_DIR, "build_exe.py"), encoding="utf-8") as f:
        build_src = f.read()
    head, _, tail = build_src.partition("VRC_Media_Streamer (Normal).bat")
    assert tail, "Normalバッチの生成箇所が見当たらない"
    line = [ln for ln in tail.splitlines() if "VRC_Media_Streamer.exe" in ln]
    assert line, "Normalバッチの起動行が見当たらない"
    assert "--tunnel" in line[0]
    for flag in ("--no-tunnel", "--headless", "--host"):
        assert flag not in line[0], f"Normalバッチが {flag} を渡している（既定値との一致が崩れる）"


# --- 初回セットアップ案内 -----------------------------------------------

def test_setup_flag_defaults_to_incomplete(dist_config):
    assert dist_config["setup_completed"] is False
    assert streamer_core.DEFAULT_CONFIG["setup_completed"] is False


def test_setup_is_pending_on_a_fresh_install():
    """新規インストール直後は案内が出る状態であること。"""
    core = streamer_core.StreamerCore()
    core.config["output_mode"] = "topaz"
    core.config["setup_completed"] = False
    assert core.is_setup_completed() is False
    assert core.get_status_data()["setup_completed"] is False


def test_generated_stream_key_does_not_count_as_setup():
    """起動時に自動生成されたキーを「設定済み」と読まないこと。

    start_background_tasks() -> ensure_stream_sink() -> ensure_stream_key() の順で、
    TopazChat では初回ポーリングより前にキーが生成・保存される。これを判定に使うと
    新規インストールで案内が一度も出ない（設計時に実際に踏んだ）。
    """
    core = streamer_core.StreamerCore()
    core.config["output_mode"] = "topaz"
    core.config["setup_completed"] = False
    core.ensure_stream_key("topaz")
    assert core.config["topaz_stream_key"], "前提: キーが生成されていること"
    assert core.is_setup_completed() is False


def test_setup_is_skipped_once_confirmed_or_non_topaz():
    core = streamer_core.StreamerCore()
    core.config["output_mode"] = "topaz"
    core.config["setup_completed"] = True
    assert core.is_setup_completed() is True

    # 自分で TopazChat 以外を選んでいる利用者には案内しない
    core.config["setup_completed"] = False
    core.config["output_mode"] = "hls"
    assert core.is_setup_completed() is True


def test_setup_modal_is_host_only_and_shown_once():
    html = _ui()
    assert 'id="setupModal"' in html, "初回セットアップのモーダルが無い"
    head, _, tail = html.partition("function maybeShowSetupModal")
    assert tail, "表示判定の関数が無い"
    body = tail[:900]
    assert "if (!isLocal) return;" in body, "ゲストにも出してしまう"
    assert "data.setup_completed !== false" in body, "未指定を「未設定」と読んでいる"
    assert "setupModalShown" in body, "ポーリングのたびに開き直す"


def test_setup_key_is_not_persisted_before_confirmation():
    """確定前にキーを保存しないこと。

    サーバーの generate_key は即座に config へ書く。案内の中で使うと
    「まだ決めていないのに保存済み」になるため、候補はブラウザ側で作る。
    """
    html = _ui()
    head, _, tail = html.partition("function generateStreamKeyCandidate")
    assert tail, "候補キーの生成関数が無い"
    body = tail[:700]
    assert "crypto.getRandomValues" in body, "推測可能な乱数を使っている"
    assert "/api/destination" not in body, "確定前にサーバーへ保存している"


def test_setup_enforces_the_minimum_key_length():
    """短いキーを弾くこと（同じキーを知る第三者に投稿を乗っ取られるため）。"""
    html = _ui()
    head, _, tail = html.partition("async function setupFinish")
    assert tail, "確定処理が無い"
    body = tail[:1200]
    assert "key.length < 32" in body, "キー長の下限を見ていない"
    assert streamer_core.STREAM_KEY_MIN_LENGTH == 32, \
        "サーバー側の下限が変わった。UI の閾値も合わせること"
    assert "setup_completed: true" in body, "確定フラグを保存していない"
