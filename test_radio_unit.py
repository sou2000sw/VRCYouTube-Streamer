import os
import sys
import time
import json
import threading
import urllib.request

from streamer_core import StreamerCore, DEFAULT_CONFIG
from api_server import APIServer

def test_radio_core():
    print("=== Testing StreamerCore Radio Mode Settings ===")
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

    # 3. set_radio_bg_source
    core.set_radio_bg_source("slideshow")
    assert core.config["radio_bg_source"] == "slideshow"
    status = core.get_status_data()
    assert status["radio_bg_source"] == "slideshow"
    print("Updated radio_bg_source:", status["radio_bg_source"])

    # 4. 背景パス取得テスト
    bg_path = core.get_radio_background_path()
    assert bg_path is not None
    assert os.path.exists(bg_path)
    print("Radio background path resolved:", bg_path)

    # 5. 元に戻す
    core.set_radio_mode(False)
    core.set_radio_bg_source("standby")
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

        # 3. POST /api/control (set_radio_bg_source: slideshow)
        body = json.dumps({"action": "set_radio_bg_source", "source": "slideshow"}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/api/control", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 200
            assert res.get("success") is True
            assert res.get("radio_bg_source") == "slideshow"
            print("API POST set_radio_bg_source response:", res)

        # 4. 再度 GET /api/status で検証
        req = urllib.request.Request(f"{base_url}/api/status")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["radio_mode"] is True
            assert data["radio_bg_source"] == "slideshow"
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

if __name__ == "__main__":
    test_radio_core()
    test_radio_api()
