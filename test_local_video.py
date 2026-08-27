import os
import io
import time
import json
import pytest
import subprocess
from unittest.mock import patch, MagicMock
from streamer_core import (
    StreamerCore,
    is_video_url_or_file,
    get_video_file_duration,
    get_ffmpeg_cmd,
    DEFAULT_CONFIG,
    VIDEO_STORAGE_DIR
)
import api_server


@pytest.fixture
def core_instance(tmp_path):
    core = StreamerCore(override_enable_tunnel=False)
    core.is_running = False
    core.set_playback_mode("video")
    core.play_queue.clear()
    core.clear_photos()
    yield core
    core.clean_hls_dir(all_files=True)


def test_is_video_url_or_file():
    """1. 動画ファイル・URLの判定テスト"""
    assert is_video_url_or_file("test.mp4") is True
    assert is_video_url_or_file("path/to/clip.mov") is True
    assert is_video_url_or_file("movie.webm") is True
    assert is_video_url_or_file("video.mkv") is True
    assert is_video_url_or_file("sample.avi") is True
    assert is_video_url_or_file("stream.ts") is True
    assert is_video_url_or_file("clip.m4v") is True
    assert is_video_url_or_file("movie.MP4?key=val#tag") is True

    assert is_video_url_or_file("photo.jpg") is False
    assert is_video_url_or_file("image.png") is False
    assert is_video_url_or_file("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False
    assert is_video_url_or_file("") is False
    assert is_video_url_or_file(None) is False


def test_add_video_file(core_instance, tmp_path):
    """2. ローカル動画ファイルのキュー追加テスト"""
    core = core_instance
    dummy_video = tmp_path / "sample_clip.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")

    with patch("streamer_core.get_video_file_duration", return_value=45.5):
        item = core.add_video_file(str(dummy_video))

    assert item is not None
    assert item["type"] == "local_video"
    assert item["is_local"] is True
    assert item["duration"] == 45.5
    assert "sample_clip" in item["title"]
    assert len(core.play_queue) == 1
    assert len(core.photo_pool) == 0  # 写真プールには混ざらないこと


def test_add_video_bytes(core_instance):
    """3. アップロード動画バイナリの保存とキュー追加テスト"""
    core = core_instance
    dummy_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"12345678"

    with patch("streamer_core.get_video_file_duration", return_value=12.0):
        item = core.add_video_bytes(dummy_bytes, original_filename="my_holiday.mp4")

    assert item is not None
    assert item["type"] == "local_video"
    assert item["is_local"] is True
    assert item["is_uploaded"] is True
    assert os.path.exists(item["path"])
    assert len(core.play_queue) == 1


def test_add_to_queue_auto_detect_local_video(core_instance, tmp_path):
    """4. add_to_queue にローカル動画パスが渡された際の自動動画判別テスト"""
    core = core_instance
    dummy_video = tmp_path / "party.webm"
    dummy_video.write_bytes(b"\x1a\x45\xdf\xa3dummy")

    with patch("streamer_core.get_video_file_duration", return_value=30.0):
        items = core.add_to_queue(str(dummy_video))

    assert len(items) == 1
    assert items[0]["type"] == "local_video"
    assert len(core.play_queue) == 1


def test_clear_queue_and_delete_uploaded_video(core_instance):
    """5. アップロードされた動画のキュー削除時ファイルクリーンアップテスト"""
    core = core_instance
    dummy_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"

    with patch("streamer_core.get_video_file_duration", return_value=10.0):
        item1 = core.add_video_bytes(dummy_bytes, original_filename="v1.mp4")
        item2 = core.add_video_bytes(dummy_bytes, original_filename="v2.mp4")

    path1 = item1["path"]
    path2 = item2["path"]
    assert os.path.exists(path1)
    assert os.path.exists(path2)

    # 1件削除
    removed = core.delete_queue_item(0)
    assert removed["id"] == item1["id"]
    assert not os.path.exists(path1)
    assert os.path.exists(path2)

    # 全削除
    core.clear_queue()
    assert not os.path.exists(path2)
    assert len(core.play_queue) == 0


def test_play_video_local_ffmpeg_cmd(core_instance, tmp_path):
    """6. play_video におけるローカル動画の FFmpeg コマンド構築検証（yt-dlpバイパス）"""
    core = core_instance
    dummy_video = tmp_path / "test_local.mp4"
    dummy_video.write_bytes(b"dummy")

    item = {
        "id": "v_test1",
        "type": "local_video",
        "title": "🎬 test_local",
        "url": str(dummy_video),
        "path": str(dummy_video),
        "duration": 60.0,
        "is_local": True
    }

    captured_cmd = None

    def mock_popen(cmd, *args, **kwargs):
        nonlocal captured_cmd
        captured_cmd = cmd
        proc = MagicMock()
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"")
        return proc

    with patch("subprocess.Popen", side_effect=mock_popen), \
         patch.object(core, "ensure_hls_receiver", return_value=True), \
         patch.object(core, "get_stream_urls") as mock_ydl:
        core.play_video(item, seek_seconds=10)

        # yt-dlp は一切呼び出されていないこと
        mock_ydl.assert_not_called()

    assert captured_cmd is not None
    # -i にローカル動画ファイルパスが直接渡されていること
    assert str(dummy_video) in captured_cmd
    # シーク -ss 10 が含まれていること
    assert "-ss" in captured_cmd
    assert "10" in captured_cmd
    # HTTP reconnect パラメータは付与されていないこと
    assert "-reconnect" not in captured_cmd


def test_play_radio_local_ffmpeg_cmd(core_instance, tmp_path):
    """7. play_radio におけるローカル動画音声の抽出配信テスト"""
    core = core_instance
    dummy_video = tmp_path / "radio_source.mp4"
    dummy_video.write_bytes(b"dummy")

    item = {
        "id": "v_radio1",
        "type": "local_video",
        "title": "🎬 radio_source",
        "url": str(dummy_video),
        "path": str(dummy_video),
        "duration": 120.0,
        "is_local": True
    }

    captured_cmd = None

    def mock_popen(cmd, *args, **kwargs):
        nonlocal captured_cmd
        captured_cmd = cmd
        proc = MagicMock()
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"")
        return proc

    with patch("subprocess.Popen", side_effect=mock_popen), \
         patch.object(core, "ensure_hls_receiver", return_value=True), \
         patch.object(core, "get_audio_only_stream_urls") as mock_ydl:
        core.play_radio(item)
        mock_ydl.assert_not_called()

    assert captured_cmd is not None
    # 音声入力 [1] としてローカル動画ファイルパスが渡されていること
    assert str(dummy_video) in captured_cmd


def test_api_upload_video_and_image(core_instance):
    """8. API /api/upload における動画（動画キュー追加）と画像（写真プール追加）の完全分離テスト"""
    core = core_instance

    class DummyServer:
        def __init__(self, core):
            self.streamer_core = core

    server = DummyServer(core)

    def create_handler(path, headers, body_bytes):
        handler = api_server.APIAndHLSHandler.__new__(api_server.APIAndHLSHandler)
        handler.streamer_core = core
        handler.path = path
        handler.headers = headers
        handler.rfile = io.BytesIO(body_bytes)
        handler.client_address = ("127.0.0.1", 12345)
        handler.command = "POST"
        handler.response_code = None
        handler.response_body = None

        def mock_send_json(code, data):
            handler.response_code = code
            handler.response_body = data

        handler.send_json_response = mock_send_json
        return handler

    # 1. 動画ファイルのアップロード
    boundary = "----WebKitFormBoundaryVideo123"
    content_type = f"multipart/form-data; boundary={boundary}"
    video_content = b"\x00\x00\x00\x18ftypmp42" + b"samplevideo"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="my_movie.mp4"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8") + video_content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Content-Length": str(len(body)),
        "Content-Type": content_type,
        "Host": "localhost:8000"
    }

    with patch("streamer_core.get_video_file_duration", return_value=15.0):
        handler = create_handler("/api/upload", headers, body)
        handler.do_POST()

    assert handler.response_code == 200
    assert handler.response_body["success"] is True
    assert handler.response_body["type"] == "video"
    assert len(core.play_queue) == 1
    assert len(core.photo_pool) == 0

    # 2. 画像ファイルのアップロード
    img_boundary = "----WebKitFormBoundaryImg123"
    img_content_type = f"multipart/form-data; boundary={img_boundary}"
    from PIL import Image
    im = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    img_body = (
        f"--{img_boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="sunset.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + img_bytes + f"\r\n--{img_boundary}--\r\n".encode("utf-8")

    img_headers = {
        "Content-Length": str(len(img_body)),
        "Content-Type": img_content_type,
        "Host": "localhost:8000"
    }

    handler_img = create_handler("/api/upload", img_headers, img_body)
    handler_img.do_POST()

    assert handler_img.response_code == 200
    assert handler_img.response_body["success"] is True
    assert handler_img.response_body["type"] == "image"
    assert len(core.play_queue) == 1
    assert len(core.photo_pool) == 1
