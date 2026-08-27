import os
import json
from streamer_core import StreamerCore, DEFAULT_CONFIG

def test_html_sync():
    print("\n--- 1. Testing HTML Synchronization ---")
    ui_path = os.path.join(os.path.dirname(__file__), "ui", "index.html")
    plugin_ui_path = os.path.join(os.path.dirname(__file__), "plugin", "ui", "index.html")

    assert os.path.exists(ui_path), "ui/index.html must exist"
    assert os.path.exists(plugin_ui_path), "plugin/ui/index.html must exist"

    with open(ui_path, "r", encoding="utf-8") as f1, open(plugin_ui_path, "r", encoding="utf-8") as f2:
        c1 = f1.read()
        c2 = f2.read()

    assert c1 == c2, "ui/index.html and plugin/ui/index.html must be identical"
    print("PASS: ui/index.html and plugin/ui/index.html are perfectly synchronized.")

def test_html_clock_elements():
    print("\n--- 2. Testing HTML Clock Elements & Constraints ---")
    ui_path = os.path.join(os.path.dirname(__file__), "ui", "index.html")
    with open(ui_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Check Clock & Badge in Header
    assert 'id="headerClock"' in content, "headerClock element must exist"
    assert 'id="headerLiveBadge"' in content, "headerLiveBadge element must exist"
    assert "JST" in content, "JST indicator must be present"
    assert "STANDBY" in content, "STANDBY default state must be present"

    # 2. Check Clock Overlay Setting
    assert 'id="settingClockOverlay"' in content, "settingClockOverlay checkbox must exist"
    assert "overlay_clock_enabled" in content, "overlay_clock_enabled must be in updateSettings"
    assert "overlay_clock_video" in content, "overlay_clock_video must be in updateSettings"

    # 3. Check JavaScript Clock Logic
    assert "function updateClock()" in content, "updateClock() function must be defined"
    assert "Asia/Tokyo" in content, "Asia/Tokyo timezone must be used"
    assert "setInterval(updateClock, 1000)" in content, "updateClock interval must be set"

    # 4. Check negative constraints (Unwanted elements must NOT exist)
    assert "遅延:" not in content, "Unwanted latency text must not exist"
    assert "バッファ:" not in content, "Unwanted buffer text must not exist"
    assert "リシンク案内コピー" not in content, "Unwanted resync button must not exist"

    print("PASS: HTML clock elements and constraints verified successfully.")

def test_streamer_core_clock_config():
    print("\n--- 3. Testing StreamerCore Clock Config & Status ---")
    assert "overlay_clock_enabled" in DEFAULT_CONFIG, "overlay_clock_enabled in DEFAULT_CONFIG"
    assert "overlay_clock_video" in DEFAULT_CONFIG, "overlay_clock_video in DEFAULT_CONFIG"

    core = StreamerCore(override_port=8998, override_enable_tunnel=False)
    try:
        # Check initial status
        status = core.get_status_data()
        assert "overlay_clock_enabled" in status, "overlay_clock_enabled in status"
        assert "overlay_clock_video" in status, "overlay_clock_video in status"

        # Check set_overlay_clock / save_config
        core.save_config({"overlay_clock_enabled": True, "overlay_clock_video": True})
        status_after = core.get_status_data()
        assert status_after["overlay_clock_enabled"] is True
        assert status_after["overlay_clock_video"] is True

        core.save_config({"overlay_clock_enabled": False, "overlay_clock_video": False})
        status_off = core.get_status_data()
        assert status_off["overlay_clock_enabled"] is False
        assert status_off["overlay_clock_video"] is False
    finally:
        core.shutdown()

    print("PASS: StreamerCore clock config and status verified successfully.")

def test_gui_clock_switch():
    print("\n--- 4. Testing GUI Streamer Clock Overlay Integration ---")
    gui_path = os.path.join(os.path.dirname(__file__), "gui_streamer.py")
    with open(gui_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "switch_clock_overlay" in content, "switch_clock_overlay must exist in gui_streamer.py"
    assert "overlay_clock_enabled" in content, "overlay_clock_enabled must be handled in gui_streamer.py"
    assert "Clock Overlay" in content, "Clock Overlay label must exist in gui_streamer.py"

    print("PASS: gui_streamer.py clock overlay integration verified successfully.")

def test_config_dist():
    print("\n--- 5. Testing config.dist.json ---")
    dist_path = os.path.join(os.path.dirname(__file__), "config.dist.json")
    with open(dist_path, "r", encoding="utf-8") as f:
        dist = json.load(f)

    assert "overlay_clock_enabled" in dist, "overlay_clock_enabled in config.dist.json"
    assert "overlay_clock_video" in dist, "overlay_clock_video in config.dist.json"

    print("PASS: config.dist.json contains clock overlay settings.")

def test_clock_filter_helpers():
    print("\n--- 6. Testing Clock Filter Helpers & Position Coordinates ---")
    from streamer_core import get_drawtext_font_path, get_live_clock_drawtext_filter, get_clock_filter_for_config

    # Font path
    font_path = get_drawtext_font_path(bold=True)
    assert font_path, "Font path must not be empty"

    # Default filter
    filter_str = get_live_clock_drawtext_filter()
    assert "drawtext=" in filter_str, "Must contain drawtext="
    assert "LIVE" in filter_str, "Must contain LIVE indicator"
    assert "localtime" in filter_str, "Must contain localtime macro"
    assert "JST" in filter_str, "Must contain JST label"
    assert "x=w-tw-45:y=26" in filter_str, "Default position must be top-right"

    # Positions
    f_tr = get_clock_filter_for_config({"overlay_clock_position": "top-right"})
    assert "x=w-tw-45:y=26" in f_tr

    f_tl = get_clock_filter_for_config({"overlay_clock_position": "top-left"})
    assert "x=45:y=26" in f_tl

    f_br = get_clock_filter_for_config({"overlay_clock_position": "bottom-right"})
    assert "x=w-tw-45:y=h-th-26" in f_br

    f_bl = get_clock_filter_for_config({"overlay_clock_position": "bottom-left"})
    assert "x=45:y=h-th-26" in f_bl

    print("PASS: Clock filter helpers and position coordinates verified.")

def test_filter_complex_clock_combinations():
    print("\n--- 7. Testing Filter Complex Builder Clock Combinations ---")
    core = StreamerCore(override_port=8998, override_enable_tunnel=False)
    try:
        clock_filter = "drawtext=test_clock"

        # 1. QR + Clock
        fc_both = core._build_video_filter_complex(has_qr=True, has_clock=True, qr_idx=2, qr_mode="bottom-right", clock_filter=clock_filter)
        assert "[v_qr];[v_qr]drawtext=test_clock[vout]" in fc_both

        # 2. QR only (No Clock)
        fc_qr_only = core._build_video_filter_complex(has_qr=True, has_clock=False, qr_idx=2, qr_mode="bottom-right", clock_filter=clock_filter)
        assert "[vout]" in fc_qr_only
        assert "drawtext" not in fc_qr_only

        # 3. Clock only (No QR)
        fc_clock_only = core._build_video_filter_complex(has_qr=False, has_clock=True, qr_idx=0, qr_mode="bottom-right", clock_filter=clock_filter)
        assert fc_clock_only == "[0:v]drawtext=test_clock[vout]"

        # 4. None
        fc_none = core._build_video_filter_complex(has_qr=False, has_clock=False, qr_idx=0, qr_mode="bottom-right", clock_filter=clock_filter)
        assert fc_none is None
    finally:
        core.shutdown()

    print("PASS: Filter complex builder clock combinations verified.")

def test_pipeline_clock_flag_respect():
    print("\n--- 8. Testing Pipeline Flag Respect (play_radio / play_image / play_standby_loop) ---")
    from unittest.mock import patch
    core = StreamerCore(override_port=8998, override_enable_tunnel=False)
    try:
        # Mock ensure_hls_receiver to True
        core.ensure_hls_receiver = lambda: True

        import tempfile
        from PIL import Image
        tmp_img = os.path.join(tempfile.gettempdir(), "test_clock_dummy.png")
        Image.new("RGB", (100, 100)).save(tmp_img)

        # 1. Test play_image with clock OFF
        core.config["overlay_clock_enabled"] = False
        core.config["overlay_clock_video"] = False
        captured_cmds = []

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = lambda cmd, *args, **kwargs: captured_cmds.append(cmd)

            core.play_image({"path": tmp_img, "duration": 5})
            assert len(captured_cmds) > 0
            img_cmd_off = captured_cmds[-1]
            assert "-vf" not in img_cmd_off, "play_image with clock OFF must NOT contain -vf"

            # Test play_image with clock ON
            core.config["overlay_clock_enabled"] = True
            core.play_image({"path": tmp_img, "duration": 5})
            img_cmd_on = captured_cmds[-1]
            assert "-vf" in img_cmd_on, "play_image with clock ON must contain -vf"
            assert any("drawtext=" in arg for arg in img_cmd_on), "play_image with clock ON must contain drawtext"

        # 2. Test play_radio with clock OFF vs ON (without QR)
        core.config["overlay_qr_enabled"] = False
        core.get_audio_only_stream_urls = lambda url: ("http://example.com/audio.mp3", "Test Audio", 100, {}, {})
        core.generate_radio_card_image = lambda meta, video_id: tmp_img

        captured_radio_cmds = []
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = lambda cmd, *args, **kwargs: captured_radio_cmds.append(cmd)

            core.config["overlay_clock_enabled"] = False
            core.play_radio({"url": "https://www.youtube.com/watch?v=test12345", "video_id": "test12345", "title": "Test Audio"})
            assert len(captured_radio_cmds) > 0
            radio_cmd_off = captured_radio_cmds[-1]
            assert "-vf" not in radio_cmd_off, "play_radio with clock OFF must NOT contain -vf"
            assert "-filter_complex" not in radio_cmd_off, "play_radio with clock OFF & QR OFF must NOT contain -filter_complex"

            core.config["overlay_clock_enabled"] = True
            core.play_radio({"url": "https://www.youtube.com/watch?v=test12345", "video_id": "test12345", "title": "Test Audio"})
            radio_cmd_on = captured_radio_cmds[-1]
            assert "-vf" in radio_cmd_on, "play_radio with clock ON & QR OFF must contain -vf"
            assert any("drawtext=" in arg for arg in radio_cmd_on), "play_radio with clock ON must contain drawtext"

        if os.path.exists(tmp_img):
            os.remove(tmp_img)
    finally:
        core.shutdown()

    print("PASS: Pipeline clock flag respect verified successfully.")

def test_drawtext_filter_actually_renders():
    """FFmpegを実際に起動し、時計フィルタが本当に描画されるかを検証する回帰テスト。

    文字列アサートだけでは、drawtext の展開エラー
    （例: 「%{localtime} requires at most 1 arguments」）によって
    実配信では何も描画されない、という不具合を検出できない。
    そのため1フレームだけ実レンダリングし、「エラーが出ないこと」と
    「実際にピクセルが変化すること」の両方を確認する。
    """
    print("")
    print("--- 9. Testing Real FFmpeg drawtext Rendering (Regression) ---")
    import shutil
    import subprocess
    import tempfile
    from streamer_core import get_ffmpeg_cmd, get_clock_filter_for_config

    ffmpeg = get_ffmpeg_cmd()
    if not (os.path.isabs(ffmpeg) and os.path.exists(ffmpeg)) and not shutil.which(ffmpeg):
        print("SKIP: ffmpeg not found.")
        return

    tmpdir = tempfile.mkdtemp(prefix="clock_render_")
    try:
        src = ["-f", "lavfi", "-i", "color=c=gray:size=640x200:rate=1"]

        # (1) フィルタ無しのベースラインを描画
        baseline = os.path.join(tmpdir, "baseline.png")
        subprocess.run([ffmpeg, "-y"] + src + ["-frames:v", "1", "-update", "1", baseline],
                       capture_output=True)
        assert os.path.exists(baseline), "baseline render must succeed"
        with open(baseline, "rb") as f:
            baseline_bytes = f.read()

        for pos in ("top-right", "top-left", "bottom-right", "bottom-left"):
            clock_filter = get_clock_filter_for_config({"overlay_clock_position": pos})
            out = os.path.join(tmpdir, "clock_%s.png" % pos)
            proc = subprocess.run(
                [ffmpeg, "-y"] + src + ["-frames:v", "1", "-update", "1", "-vf", clock_filter, out],
                capture_output=True)
            stderr = proc.stderr.decode("utf-8", errors="replace")

            assert proc.returncode == 0, "ffmpeg must succeed (%s): %s" % (pos, stderr[-400:])
            # drawtext の展開・解析エラーが1件も出ていないこと
            for ng in ("requires at most", "Error parsing", "Invalid argument", "No such filter"):
                assert ng not in stderr, "drawtext error (%s): %s" % (pos, ng)
            assert os.path.exists(out), "clock render must produce output (%s)" % pos
            # ベースラインと異なる = 実際にピクセルが描画されている
            with open(out, "rb") as f:
                rendered = f.read()
            assert rendered != baseline_bytes, "clock overlay must actually draw pixels (%s)" % pos

        print("PASS: drawtext clock overlay renders for all 4 positions.")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == "__main__":
    test_html_sync()
    test_html_clock_elements()
    test_streamer_core_clock_config()
    test_gui_clock_switch()
    test_config_dist()
    test_clock_filter_helpers()
    test_filter_complex_clock_combinations()
    test_pipeline_clock_flag_respect()
    test_drawtext_filter_actually_renders()
    print("\n==============================================")
    print("ALL CLOCK FEATURE UNIT TESTS PASSED!")
    print("==============================================")

