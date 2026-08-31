# -*- coding: utf-8 -*-
"""設定オーバーライドの優先順位と永続化分離のテスト（タスク19）。

守りたい不変条件は2つ:

1. **CLI / 環境変数で与えた値は config.json に書かれない。**
   その起動限りの指定が焼き付くと、`--no-tunnel` で一度テストしただけで
   トンネル無効が恒久設定になる（実際に起きていた）。
2. **利用者が明示的に変更した値は、ちゃんと保存され、その起動でも反映される。**
   1を守ろうとして変更まで無視してしまうと「保存したのに反映されない」になる。
"""

import argparse
import io
import json
import os

import pytest

import streamer_core
from streamer_core import DEFAULT_CONFIG, LayeredConfig, StreamerCore
from config_overrides import (
    ENV_PREFIX,
    SECRET_KEYS,
    add_config_arguments,
    build_overrides,
    collect_env_overrides,
    parse_set_assignments,
)


# ------------------------------------------------------------------
# ヘルパー
# ------------------------------------------------------------------

def make_parser():
    """gui_streamer.main() と同じ引数構成の parser を組む。

    args を手作りしたモックで済ませると、argparse の dest 名の取り違え
    （--no-tunnel → no_tunnel、--set → set_values 等）を見逃す。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", "-hl", action="store_true")
    parser.add_argument("--tunnel", action="store_true")
    parser.add_argument("--no-tunnel", "-nt", action="store_true")
    parser.add_argument("--port", "-p", type=int, default=None)
    parser.add_argument("--host", type=str, default=None)
    add_config_arguments(parser)
    return parser


def parse(argv):
    return make_parser().parse_args(argv)


def make_core(tmp_path, overrides=None, seed=None, name="config.json"):
    """一時 config.json を使うコアを作る。"""
    path = str(tmp_path / name)
    if seed is not None:
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(seed, f)
    core = StreamerCore(overrides=overrides, config_path=path)
    core.is_running = False
    return core, path


def read_json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# 1〜4, 12, 13, 15: 永続化分離と優先順位（StreamerCore 越し）
# ------------------------------------------------------------------

def test_override_not_persisted(tmp_path):
    core, path = make_core(tmp_path, overrides={"port": (9999, "cli")})
    core.save_config({"loop_queue": True})

    saved = read_json(path)
    assert saved["port"] != 9999, "CLI指定の port が config.json へ焼き付いてはいけない"
    assert saved["loop_queue"] is True, "利用者が変更した値は保存されること"
    assert core.config["port"] == 9999, "その起動中は CLI 指定が効いていること"


def test_echoed_override_not_persisted(tmp_path):
    """Bug-1 の回帰テスト。

    設定画面はフォーム全体を送り返すため、利用者が触っていない enable_tunnel も
    実効値（＝CLI指定値）のまま POST されてくる。これを「変更」と扱うと焼き付く。
    """
    core, path = make_core(tmp_path, overrides={"enable_tunnel": (False, "cli")})
    assert core.config["enable_tunnel"] is False

    core.save_config({"enable_tunnel": False, "image_display_duration": 30})

    saved = read_json(path)
    assert saved["enable_tunnel"] is True, "エコーされただけの上書き値を永続化してはいけない"
    assert saved["image_display_duration"] == 30, "同時に送られた本当の変更は保存すること"
    assert core.config["enable_tunnel"] is False, "その起動中は CLI 指定のまま"


def test_explicit_change_releases_override(tmp_path):
    core, path = make_core(tmp_path, overrides={"enable_tunnel": (False, "cli")})

    core.save_config({"enable_tunnel": True})

    assert read_json(path)["enable_tunnel"] is True
    assert core.config["enable_tunnel"] is True, "明示的な変更はその起動でも反映すること"
    assert core.config.is_overridden("enable_tunnel") is False


def test_precedence_cli_over_file_over_default(tmp_path):
    # (a) config.json の値が既定値に勝つ
    core_a, _ = make_core(tmp_path, seed={"port": 8123}, name="a.json")
    assert core_a.config["port"] == 8123

    # (b) CLI 指定が config.json に勝つ
    core_b, _ = make_core(tmp_path, overrides={"port": (9000, "cli")},
                          seed={"port": 8123}, name="b.json")
    assert core_b.config["port"] == 9000

    # (c) どちらも無ければ既定値
    core_c, _ = make_core(tmp_path, seed={}, name="c.json")
    assert core_c.config["port"] == DEFAULT_CONFIG["port"]


def test_internal_setter_persists_while_override_active(tmp_path):
    core, path = make_core(tmp_path, overrides={"port": (9000, "cli")})

    core.config["loop_queue"] = True
    core.save_config()

    saved = read_json(path)
    assert saved["loop_queue"] is True
    assert saved["port"] != 9000, "上書き中のキーは、他の保存に巻き込まれて焼き付いてはいけない"


def test_enable_tunnel_property(tmp_path):
    core, path = make_core(tmp_path, overrides={"enable_tunnel": (False, "cli")})
    assert core.enable_tunnel is False

    # 代入は永続層への記録。上書きが生きている間は実効値を変えない。
    core.enable_tunnel = True
    assert core.enable_tunnel is False

    core.save_config()
    assert read_json(path)["enable_tunnel"] is True


def test_config_path_isolation(tmp_path):
    """config_path を渡したコアは、既定の CONFIG_FILE を一切触らないこと。"""
    default_path = streamer_core.CONFIG_FILE
    before = read_json(default_path) if os.path.exists(default_path) else None

    core, _ = make_core(tmp_path, name="isolated.json")
    core.save_config({"loop_queue": True})

    after = read_json(default_path) if os.path.exists(default_path) else None
    assert after == before, "別の config_path を指定したコアが既定の config.json を書き換えた"


# ------------------------------------------------------------------
# 5, 6, 11: 環境変数
# ------------------------------------------------------------------

def test_env_var_override():
    result = collect_env_overrides({ENV_PREFIX + "PORT": "8321"})
    assert result == {"port": 8321}
    assert isinstance(result["port"], int)


def test_cli_beats_env():
    overrides = build_overrides(parse(["--port", "8080"]),
                                environ={ENV_PREFIX + "PORT": "8321"})
    assert overrides["port"] == (8080, "cli")


def test_secret_accepted_via_env():
    result = collect_env_overrides({ENV_PREFIX + "TOPAZ_STREAM_KEY": "abcdef"})
    assert result == {"topaz_stream_key": "abcdef"}


def test_env_ignores_unknown_and_malformed():
    """環境変数は他用途と偶然衝突しうるので、起動を止めずそのキーだけ捨てる。"""
    result = collect_env_overrides({
        ENV_PREFIX + "BOGUS_KEY": "1",
        ENV_PREFIX + "LOOP_QUEUE": "maybe",
        ENV_PREFIX + "PORT": "8100",
    })
    assert result == {"port": 8100}


# ------------------------------------------------------------------
# 7〜10: --set
# ------------------------------------------------------------------

def test_set_flag_type_coercion():
    result = parse_set_assignments(
        ["loop_queue=true", "port=8080", "overlay_clock_position=top-left"]
    )
    assert result["loop_queue"] is True
    assert isinstance(result["loop_queue"], bool)
    assert result["port"] == 8080
    assert isinstance(result["port"], int) and not isinstance(result["port"], bool)
    assert result["overlay_clock_position"] == "top-left"
    assert isinstance(result["overlay_clock_position"], str)


def test_set_flag_rejects_unknown_key():
    with pytest.raises(ValueError):
        parse_set_assignments(["nope=1"])


def test_set_flag_rejects_bad_bool():
    with pytest.raises(ValueError):
        parse_set_assignments(["loop_queue=maybe"])


def test_set_flag_rejects_missing_equals():
    with pytest.raises(ValueError):
        parse_set_assignments(["port"])


def test_secret_keys_rejected_via_set():
    """コマンドライン引数は他の利用者からプロセス一覧で見えるため、秘匿値を載せない。"""
    for key in SECRET_KEYS:
        with pytest.raises(ValueError) as excinfo:
            parse_set_assignments([f"{key}=x"])
        assert ENV_PREFIX in str(excinfo.value), "環境変数を使うよう案内すること"


# ------------------------------------------------------------------
# 14, 16: 複数キーへ展開されるフラグ
# ------------------------------------------------------------------

def test_resolution_flag():
    overrides = build_overrides(parse(["--resolution", "1920x1080"]), environ={})
    assert overrides["rtmp_video_width"] == (1920, "cli")
    assert overrides["rtmp_video_height"] == (1080, "cli")

    with pytest.raises(SystemExit):      # argparse は不正な type= を SystemExit にする
        parse(["--resolution", "abc"])


def test_radio_flags():
    on = build_overrides(parse(["--radio"]), environ={})
    assert on["playback_mode"] == ("radio", "cli")
    assert on["radio_mode"] == (True, "cli")

    off = build_overrides(parse(["--no-radio"]), environ={})
    assert off["playback_mode"] == ("video", "cli")
    assert off["radio_mode"] == (False, "cli")

    with pytest.raises(ValueError):
        build_overrides(parse(["--radio", "--no-radio"]), environ={})


def test_output_mode_and_rate_flags():
    overrides = build_overrides(
        parse(["--output-mode", "generic_rtmp", "--bitrate", "2500", "--fps", "60"]),
        environ={},
    )
    assert overrides["output_mode"] == ("generic_rtmp", "cli")
    assert overrides["rtmp_video_bitrate_kbps"] == (2500, "cli")
    assert overrides["rtmp_fps"] == (60, "cli")


def test_tunnel_flags():
    assert build_overrides(parse(["--no-tunnel"]), environ={})["enable_tunnel"] == (False, "cli")
    assert build_overrides(parse(["--tunnel"]), environ={})["enable_tunnel"] == (True, "cli")
    assert "enable_tunnel" not in build_overrides(parse([]), environ={})


# ------------------------------------------------------------------
# 17: LayeredConfig 単体
# ------------------------------------------------------------------

def test_persistable_excludes_overrides():
    cfg = LayeredConfig(DEFAULT_CONFIG)
    cfg.set_override("port", 9999, "cli")

    assert cfg["port"] == 9999, "実効値としては上書きが最優先"

    persisted = cfg.persistable()
    assert set(DEFAULT_CONFIG).issubset(persisted), "既定値の項目が保存内容から消えてはいけない"
    assert persisted["port"] != 9999, "上書きは保存内容に含めない"
    assert persisted["port"] == DEFAULT_CONFIG["port"]
