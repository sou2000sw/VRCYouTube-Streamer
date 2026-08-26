import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:8888"

def make_request(method, path, data=None, headers=None):
    url = f"{BASE_URL}{path}"
    req_headers = headers.copy() if headers else {}
    body = None
    if data is not None:
        req_headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8")
        return e.code, json.loads(resp_body) if resp_body else {"error": str(e)}

def run_security_tests():
    print("=== Security Test 1: Local Access & Config Update ===")
    status, res = make_request("GET", "/api/config")
    print(f"GET /api/config from local ({status})")
    assert status == 200

    print("\n=== Security Test 2: Remote Simulation (CF-Connecting-IP) ===")
    remote_headers = {"CF-Connecting-IP": "203.0.113.195"}

    # 1. Remote status read (Should be allowed)
    status, res = make_request("GET", "/api/status", headers=remote_headers)
    print(f"Remote GET /api/status -> {status}")
    assert status == 200
    assert "permissions" in res

    # 2. Remote shutdown attempt (Should be 403 Forbidden)
    status, res = make_request("POST", "/api/shutdown", {}, headers=remote_headers)
    print(f"Remote POST /api/shutdown -> {status}: {res.get('message')}")
    assert status == 403

    # 3. Remote config modification attempt (Should be 403 Forbidden)
    status, res = make_request("POST", "/api/config", {"port": 9999}, headers=remote_headers)
    print(f"Remote POST /api/config -> {status}: {res.get('message')}")
    assert status == 403

    # 4. Remote clear_queue destruction attempt (Should be 403 Forbidden)
    status, res = make_request("POST", "/api/control", {"action": "clear_queue"}, headers=remote_headers)
    print(f"Remote POST /api/control (clear_queue) -> {status}: {res.get('message')}")
    assert status == 403

    # 5. SSRF / Local file exploit attempt via /api/queue (Should be 400 Bad Request)
    status, res = make_request("POST", "/api/queue", {"url": "file:///C:/Windows/System32/drivers/etc/hosts"}, headers=remote_headers)
    print(f"Remote POST /api/queue (file:// exploit) -> {status}: {res.get('message')}")
    assert status == 400

    # 5.5. Rate limit spam attempt immediately after previous request (Should be 429 Too Many Requests)
    status, res = make_request("POST", "/api/queue", {"url": "https://example.com/dummy"}, headers=remote_headers)
    print(f"Remote POST /api/queue (Spam within 2.5s) -> {status}: {res.get('message')}")
    assert status == 429

    time.sleep(2.6)

    # 6. Safe Remote Video Add (Should succeed when allow_web_queue_add is True)
    status, res = make_request("POST", "/api/queue", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, headers=remote_headers)
    print(f"Remote POST /api/queue (Safe URL) -> {status}")
    assert status == 200

    print("\n=== Security Test 3: Granular Web Permissions ===")
    # Disable playback control and queue edit from host
    make_request("POST", "/api/config", {
        "allow_web_playback_control": False,
        "allow_web_queue_edit": False,
        "allow_web_queue_add": False
    })

    # Test Remote skip when disallowed (Should be 403)
    status, res = make_request("POST", "/api/control", {"action": "skip"}, headers=remote_headers)
    print(f"Remote POST /api/control (skip when disallowed) -> {status}: {res.get('message')}")
    assert status == 403

    # Test Remote delete when disallowed (Should be 403)
    status, res = make_request("POST", "/api/control", {"action": "delete_item", "index": 0}, headers=remote_headers)
    print(f"Remote POST /api/control (delete when disallowed) -> {status}: {res.get('message')}")
    assert status == 403

    # Test Remote add when disallowed (Should be 403)
    time.sleep(2.6)
    status, res = make_request("POST", "/api/queue", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, headers=remote_headers)
    print(f"Remote POST /api/queue (add when disallowed) -> {status}: {res.get('message')}")
    assert status == 403

    # Re-enable permissions
    make_request("POST", "/api/config", {
        "allow_web_playback_control": True,
        "allow_web_queue_edit": True,
        "allow_web_queue_add": True
    })

    # Test Remote skip when allowed (Should be 200)
    status, res = make_request("POST", "/api/control", {"action": "skip"}, headers=remote_headers)
    print(f"Remote POST /api/control (skip when allowed) -> {status}")
    assert status == 200

    print("\n=== Security Test 4: Web PIN / Password Protection ===")
    # 1. パスワードを設定
    make_request("POST", "/api/config", {"web_password": "secret1234"})

    # 2. ローカルからのアクセスはパスワード未付与でもアクセス可能 (バイパス)
    status, res = make_request("GET", "/api/status")
    print(f"Local GET /api/status without password -> {status}")
    assert status == 200
    assert res.get("has_web_password") is True

    # 3. リモートからのアクセス（パスワードなし）-> 401 Unauthorized
    status, res = make_request("GET", "/api/status", headers=remote_headers)
    print(f"Remote GET /api/status without password -> {status}")
    assert status == 401
    assert res.get("has_web_password") is True

    # 4. リモートからの認証エンドポイント検証 (誤ったパスワード -> 401)
    status, res = make_request("POST", "/api/auth", {"password": "wrong_password"}, headers=remote_headers)
    print(f"Remote POST /api/auth (wrong password) -> {status}")
    assert status == 401

    # 5. リモートからの認証エンドポイント検証 (正しいパスワード -> 200)
    status, res = make_request("POST", "/api/auth", {"password": "secret1234"}, headers=remote_headers)
    print(f"Remote POST /api/auth (correct password) -> {status}")
    assert status == 200

    # 6. リモートから正しい X-Web-Password ヘッダー付きでアクセス -> 200
    authed_headers = {"CF-Connecting-IP": "203.0.113.195", "X-Web-Password": "secret1234"}
    status, res = make_request("GET", "/api/status", headers=authed_headers)
    print(f"Remote GET /api/status with X-Web-Password -> {status}")
    assert status == 200

    status, res = make_request("POST", "/api/control", {"action": "skip"}, headers=authed_headers)
    print(f"Remote POST /api/control with X-Web-Password -> {status}")
    assert status == 200

    # 7. パスワードを空文字にリセット（認証無効化）
    make_request("POST", "/api/config", {"web_password": ""})
    status, res = make_request("GET", "/api/status", headers=remote_headers)
    print(f"Remote GET /api/status after clearing password -> {status}")
    assert status == 200
    assert res.get("has_web_password") is False

    print("\n=== Security Test 5: Local Shutdown ===")
    status, res = make_request("POST", "/api/shutdown", {})
    print(f"Local POST /api/shutdown -> {status}")
    assert status == 200

    print("\n ALL SECURITY & PERMISSION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_security_tests()
