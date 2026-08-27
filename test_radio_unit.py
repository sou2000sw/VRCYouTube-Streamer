import os
import sys
import io
import time
import json
import threading
import urllib.request
from PIL import Image

from streamer_core import (
    StreamerCore, DEFAULT_CONFIG, RADIO_CACHE_DIR, STANDBY_IMAGE_PATH,
    get_drawtext_font_path, get_live_clock_drawtext_filter, get_pil_font
)
from api_server import APIServer

def test_radio_card_generation():
    print("\n=== Testing StreamerCore Radio Card Visualizer Generation ===")
    core = StreamerCore(override_port=8999, override_enable_tunnel=False)
    
    mock_video_info = {
        "url": "https://www.youtube.com/watch?v=TEST_VIDEO_123",
        "title": "🎵 テスト楽曲タイトル - Long Title for Testing Wrapping Feature",
        "duration": 215
    }
    mock_meta = {
        "id": "TEST_VIDEO_123",
        "title": "🎵 テスト楽曲タイトル - Long Title for Testing Wrapping Feature",
        "duration": 215,
        "artist": "テストアーティスト名 (Test Artist)",
        "channel": "Test Channel Official",
        "thumbnail": ""
    }

    # 1. カード画像生成
    card_path = core.generate_radio_card_image(mock_video_info, mock_meta)
    assert card_path is not None
    assert os.path.exists(card_path)
    print("Generated radio card path:", card_path)

    # 2. 画像サイズとフォーマットの検証 (1920x1080)
    with Image.open(card_path) as img:
        assert img.size == (1920, 1080)
        assert img.format == "PNG"
        print(f"Verified image dimensions: {img.size} ({img.format})")

    # 3. get_radio_background_path での取得検証
    core.set_radio_bg_source("card")
    bg_path = core.get_radio_background_path(mock_video_info, mock_meta)
    assert bg_path == card_path
    print("Resolved background path matches generated card:", bg_path)

    core.shutdown()
    print("[PASS] Radio Card Visualizer Generation Tests Passed!")

def test_radio_core():
    print("\n=== Testing StreamerCore Radio Mode Settings ===")
    core = StreamerCore(override_port=8999, override_enable_tunnel=False)
    
    # 1. 初期状態チェック
    status = core.get_status_data()
    assert "radio_mode" in status
    assert "radio_bg_source" in status
    print("Initial status radio_mode:", status["radio_mode"])
    print("Initial status radio_bg_source:", status["radio_bg_source"])

    # 2. set_radio_mode
    core.set_radio_mode(True)
    assert core.config["radio_mode"] is True
    status = core.get_status_data()
    assert status["radio_mode"] is True
    print("Updated radio_mode:", status["radio_mode"])

    # 3. set_radio_bg_source ("card", "slideshow", "standby")
    for src in ("slideshow", "standby", "card"):
        core.set_radio_bg_source(src)
        assert core.config["radio_bg_source"] == src
        status = core.get_status_data()
        assert status["radio_bg_source"] == src
        print(f"Updated radio_bg_source to '{src}': verified")

    # 4. 背景パス取得テスト (デフォルト待機)
    core.set_radio_bg_source("standby")
    bg_path = core.get_radio_background_path()
    assert bg_path is not None
    assert os.path.exists(bg_path)
    print("Radio background path resolved:", bg_path)

    # 5. 元に戻す
    core.set_radio_mode(False)
    core.set_radio_bg_source("card")
    core.shutdown()
    print("[PASS] StreamerCore Radio Unit Tests Passed!")

def test_radio_api():
    print("\n=== Testing APIServer Radio Mode Endpoints ===")
    core = StreamerCore(override_port=8998, override_enable_tunnel=False)
    server = APIServer(core)
    server.start()
    time.sleep(1)

    try:
        base_url = "http://127.0.0.1:8998"

        # 1. GET /api/status
        req = urllib.request.Request(f"{base_url}/api/status")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 200
            assert "radio_mode" in data
            assert "radio_bg_source" in data
            print("API GET /api/status radio_mode:", data["radio_mode"])

        # 2. POST /api/control (set_radio_mode: true)
        body = json.dumps({"action": "set_radio_mode", "enabled": True}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/api/control", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 200
            assert res.get("success") is True
            assert res.get("radio_mode") is True
            print("API POST set_radio_mode response:", res)

        # 3. POST /api/control (set_radio_bg_source: card)
        body = json.dumps({"action": "set_radio_bg_source", "source": "card"}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/api/control", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 200
            assert res.get("success") is True
            assert res.get("radio_bg_source") == "card"
            print("API POST set_radio_bg_source (card) response:", res)

        # 4. 再度 GET /api/status で検証
        req = urllib.request.Request(f"{base_url}/api/status")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["radio_mode"] is True
            assert data["radio_bg_source"] == "card"
            print("Verified updated status via API:", data["radio_mode"], data["radio_bg_source"])

        # 5. POST /api/shutdown
        body = json.dumps({}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/api/shutdown", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200

        print("[PASS] APIServer Radio Endpoints Tests Passed!")

    finally:
        server.stop()
        core.shutdown()

def test_radio_slideshow_advance():
    print("\n=== Testing Radio Mode Slideshow Auto Advance ===")
    core = StreamerCore(override_port=8997, override_enable_tunnel=False)
    
    # テスト用ダミー画像作成
    test_img1 = Image.new("RGB", (800, 600), color=(255, 0, 0))
    test_img2 = Image.new("RGB", (800, 600), color=(0, 255, 0))
    
    buf1 = io.BytesIO()
    test_img1.save(buf1, format="PNG")
    p1 = core.add_image_bytes(buf1.getvalue(), "test_photo_1.png")
    buf2 = io.BytesIO()
    test_img2.save(buf2, format="PNG")
    p2 = core.add_image_bytes(buf2.getvalue(), "test_photo_2.png")
    
    assert p1 is not None and os.path.exists(p1["path"])
    assert p2 is not None and os.path.exists(p2["path"])
    
    # 1. get_slideshow_images で画像が取得できるか
    images = core.get_slideshow_images()
    assert len(images) >= 2
    print(f"Discovered {len(images)} slideshow images:", images[:2])
    
    # 2. 自動送りが有効な設定での動作確認
    core.set_radio_mode(True)
    core.set_radio_bg_source("slideshow")
    core.set_image_auto_advance(True)
    core.set_image_duration(10)
    
    assert core.config["radio_bg_source"] == "slideshow"
    assert core.config["image_auto_advance"] is True
    assert core.config["image_display_duration"] == 10
    
    # 一時画像ファイルのクリーンアップ
    for p in (p1["path"], p2["path"]):
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    core.clear_photos()

    core.shutdown()
    print("[PASS] Radio Mode Slideshow Auto Advance Tests Passed!")

def test_live_clock_and_resync_overlay():
    print("\n=== Testing Live Clock & Resync Guide Helpers ===")
    
    # 1. Helper functions
    font_path = get_drawtext_font_path(bold=True)
    assert font_path is not None and len(font_path) > 0
    print("Detected drawtext font path:", font_path)

    clock_filter = get_live_clock_drawtext_filter(x="w-tw-45", y="26", font_size=28)
    assert "drawtext=" in clock_filter
    assert "text='● LIVE %{localtime\\:%H\\:%M\\:%S} JST'" in clock_filter
    assert "boxcolor=0x0F172A@0.82" in clock_filter
    assert "fontsize=28" in clock_filter
    print("Generated live clock drawtext filter:", clock_filter)

    pil_font = get_pil_font(24, bold=True)
    assert pil_font is not None

    # 2. Config defaults
    assert "overlay_clock_enabled" in DEFAULT_CONFIG
    assert "overlay_clock_video" in DEFAULT_CONFIG
    assert "overlay_clock_position" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["overlay_clock_position"] == "top-right"

    core = StreamerCore(override_port=8996, override_enable_tunnel=False)
    status = core.get_status_data()
    assert "overlay_clock_enabled" in status
    assert "overlay_clock_video" in status
    assert "overlay_clock_position" in status

    # 3. set_overlay_clock
    core.set_overlay_clock(True, video=True, position="top-right")
    assert core.config["overlay_clock_enabled"] is True
    assert core.config["overlay_clock_video"] is True
    assert core.config["overlay_clock_position"] == "top-right"

    # 4. Standby image generation with resync guide footer
    core.generate_standby_image()
    assert os.path.exists(STANDBY_IMAGE_PATH)
    with Image.open(STANDBY_IMAGE_PATH) as img:
        assert img.size == (1920, 1080)
        assert img.format == "PNG"

    core.shutdown()
    print("[PASS] Live Clock & Resync Guide Tests Passed!")

if __name__ == "__main__":
    test_radio_card_generation()
    test_radio_core()
    test_radio_api()
    test_radio_slideshow_advance()
    test_live_clock_and_resync_overlay()

