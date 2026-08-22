import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:8888"

def make_request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8")
        return e.code, json.loads(resp_body) if resp_body else {"error": str(e)}

def run_tests():
    print("=== 1. Testing GET /api/status ===")
    status_code, data = make_request("GET", "/api/status")
    print(f"Status ({status_code}):", json.dumps(data, indent=2))
    assert status_code == 200
    assert "status" in data
    assert "queue" in data
    assert "loop_queue" in data
    assert "shuffle" in data

    print("\n=== 2. Testing POST /api/control (set_loop: true) ===")
    status_code, loop_res = make_request("POST", "/api/control", {"action": "set_loop", "enabled": True})
    print(f"Set Loop ({status_code}):", json.dumps(loop_res, indent=2))
    assert status_code == 200
    assert loop_res.get("loop_queue") is True

    print("\n=== 3. Testing POST /api/control (set_shuffle: true) ===")
    status_code, shuf_res = make_request("POST", "/api/control", {"action": "set_shuffle", "enabled": True})
    print(f"Set Shuffle ({status_code}):", json.dumps(shuf_res, indent=2))
    assert status_code == 200
    assert shuf_res.get("shuffle") is True

    print("\n=== 4. Testing POST /api/control (shuffle now) ===")
    status_code, shuf_now = make_request("POST", "/api/control", {"action": "shuffle"})
    print(f"Shuffle Now ({status_code}):", json.dumps(shuf_now, indent=2))
    assert status_code == 200
    assert shuf_now.get("success") is True

    print("\n=== 5. Testing POST /api/queue (Adding video) ===")
    status_code, add_res = make_request("POST", "/api/queue", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    print(f"Queue Add ({status_code}):", json.dumps(add_res, indent=2))
    assert status_code == 200
    assert add_res.get("success") is True

    print("\n=== 6. Testing GET /api/status after queue add ===")
    time.sleep(2)
    status_code, data = make_request("GET", "/api/status")
    print(f"Status ({status_code}):", json.dumps(data, indent=2))
    assert data.get("loop_queue") is True
    assert data.get("shuffle") is True

    print("\n=== 7. Testing POST /api/control (Action: skip with loop enabled) ===")
    status_code, ctrl_res = make_request("POST", "/api/control", {"action": "skip"})
    print(f"Control ({status_code}):", json.dumps(ctrl_res, indent=2))
    assert status_code == 200
    assert ctrl_res.get("success") is True

    print("\n=== 8. Testing POST /api/control (Action: clear_queue) ===")
    status_code, clr_res = make_request("POST", "/api/control", {"action": "clear_queue"})
    print(f"Clear Queue ({status_code}):", json.dumps(clr_res, indent=2))
    assert status_code == 200

    print("\n=== 9. Testing POST /api/shutdown ===")
    status_code, shut_res = make_request("POST", "/api/shutdown")
    print(f"Shutdown ({status_code}):", json.dumps(shut_res, indent=2))
    assert status_code == 200
    assert shut_res.get("success") is True

    print("\n All Shuffle & Loop API tests passed successfully!")

if __name__ == "__main__":
    run_tests()
