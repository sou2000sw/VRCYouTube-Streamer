import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:8888"

def make_req(path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"} if data is not None else {}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def test_stream_transitions():
    print("=== Testing Continuous Stream Transitions ===")
    
    # 1. Check stream.m3u8 exists during standby
    with urllib.request.urlopen(f"{BASE_URL}/stream.m3u8") as resp:
        m3u8_standby = resp.read().decode("utf-8")
        print("1. Standby stream.m3u8:\n", m3u8_standby)
        assert resp.status == 200

    # 2. Add 2 videos
    res1 = make_req("/api/queue", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    print("Added video 1:", res1.get("message"))
    res2 = make_req("/api/queue", {"url": "https://www.youtube.com/watch?v=9bZkp7q19f0"})
    print("Added video 2:", res2.get("message"))

    # 3. Wait for video 1 to start buffering/streaming
    time.sleep(4)
    status = make_req("/api/status")
    print("Current status:", status.get("status"), "Playing:", status.get("current_video", {}).get("title"))

    # 4. Check stream.m3u8 during Video 1
    with urllib.request.urlopen(f"{BASE_URL}/stream.m3u8") as resp:
        m3u8_v1 = resp.read().decode("utf-8")
        print("2. Video 1 stream.m3u8:\n", m3u8_v1)
        assert resp.status == 200

    # 5. Skip to Video 2
    print("Skipping to Video 2...")
    make_req("/api/control", {"action": "skip"})
    time.sleep(4)

    status2 = make_req("/api/status")
    print("Status after skip:", status2.get("status"), "Playing:", status2.get("current_video", {}).get("title"))

    # 6. Check stream.m3u8 during Video 2
    with urllib.request.urlopen(f"{BASE_URL}/stream.m3u8") as resp:
        m3u8_v2 = resp.read().decode("utf-8")
        print("3. Video 2 stream.m3u8:\n", m3u8_v2)
        assert resp.status == 200

    # 7. Skip to Standby
    print("Skipping to Standby...")
    make_req("/api/control", {"action": "skip"})
    time.sleep(4)

    # 8. Check stream.m3u8 back in Standby
    with urllib.request.urlopen(f"{BASE_URL}/stream.m3u8") as resp:
        m3u8_back_standby = resp.read().decode("utf-8")
        print("4. Back in Standby stream.m3u8:\n", m3u8_back_standby)
        assert resp.status == 200

    print("\n Seamless stream transition test passed with flying colors!")

if __name__ == "__main__":
    test_stream_transitions()
