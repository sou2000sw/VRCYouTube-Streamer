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

if __name__ == "__main__":
    test_html_sync()
    test_html_clock_elements()
    test_streamer_core_clock_config()
    test_gui_clock_switch()
    test_config_dist()
    print("\n==============================================")
    print("ALL CLOCK FEATURE UNIT TESTS PASSED!")
    print("==============================================")
