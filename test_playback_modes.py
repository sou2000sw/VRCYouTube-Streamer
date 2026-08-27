import os
import io
import json
import pytest
from PIL import Image
from streamer_core import StreamerCore, DEFAULT_CONFIG, STANDBY_IMAGE_PATH, IMAGE_CACHE_DIR


def create_dummy_png_bytes(width=100, height=100, color="red"):
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def core_instance(tmp_path):
    # テスト用のStreamerCoreインスタンス
    core = StreamerCore(override_enable_tunnel=False)
    core.is_running = False  # バックグラウンドスレッドを立ち上げない
    core.set_playback_mode("video")
    core.play_queue.clear()
    core.clear_photos()
    yield core
    core.clean_hls_dir(all_files=True)


def test_playback_mode_switching(core_instance):
    """1. 再生モードの切り替えと後方互換性テスト"""
    core = core_instance

    # 初期状態は video
    assert core.get_playback_mode() == "video"
    assert core.config.get("radio_mode") is False

    # radio に切り替え
    res = core.set_playback_mode("radio")
    assert res == "radio"
    assert core.get_playback_mode() == "radio"
    assert core.config.get("radio_mode") is True

    # slideshow に切り替え
    res = core.set_playback_mode("slideshow")
    assert res == "slideshow"
    assert core.get_playback_mode() == "slideshow"
    assert core.config.get("radio_mode") is False

    # set_radio_mode(True) 後方互換性
    core.set_radio_mode(True)
    assert core.get_playback_mode() == "radio"
    assert core.config.get("radio_mode") is True

    # set_radio_mode(False) 後方互換性
    core.set_radio_mode(False)
    assert core.get_playback_mode() == "video"
    assert core.config.get("radio_mode") is False

    # 不正なモードの拒絶
    core.set_playback_mode("invalid_mode")
    assert core.get_playback_mode() == "video"


def test_photo_pool_separation(core_instance):
    """2. 動画キューと写真プールの完全分離テスト"""
    core = core_instance

    png_bytes = create_dummy_png_bytes(color="blue")
    item = core.add_image_bytes(png_bytes, original_filename="test_pic.png")

    assert item is not None
    # 写真は photo_pool に追加され、play_queue には入らない
    assert len(core.play_queue) == 0
    assert len(core.photo_pool) == 1
    assert core.photo_pool[0]["id"].startswith("p_")
    assert "test_pic" in core.photo_pool[0]["title"]
    assert os.path.exists(core.photo_pool[0]["path"])

    # 動画アイテムをキューに追加したと仮定
    video_item = {"type": "video", "title": "Test Video", "url": "https://www.youtube.com/watch?v=dummy", "duration": 120}
    core.play_queue.append(video_item)

    assert len(core.play_queue) == 1
    assert len(core.photo_pool) == 1

    # play_queue をクリアしても photo_pool は消えない
    core.clear_queue()
    assert len(core.play_queue) == 0
    assert len(core.photo_pool) == 1


def test_photo_pool_crud(core_instance):
    """3. 写真プールの取得・並び替え・個別削除・一括削除テスト"""
    core = core_instance

    # 3枚追加
    p1 = core.add_image_bytes(create_dummy_png_bytes(color="red"), original_filename="photo1.png")
    p2 = core.add_image_bytes(create_dummy_png_bytes(color="green"), original_filename="photo2.png")
    p3 = core.add_image_bytes(create_dummy_png_bytes(color="blue"), original_filename="photo3.png")

    photos = core.get_photos()
    assert len(photos) == 3
    assert photos[0]["id"] == p1["id"]
    assert photos[1]["id"] == p2["id"]
    assert photos[2]["id"] == p3["id"]

    # 並び替え: 0番目を2番目に移動 (p1 が末尾へ)
    ok = core.move_photo(0, 2)
    assert ok is True
    photos = core.get_photos()
    assert photos[0]["id"] == p2["id"]
    assert photos[1]["id"] == p3["id"]
    assert photos[2]["id"] == p1["id"]

    # 個別削除: p2 (先頭) を ID で削除
    p2_path = p2["path"]
    assert os.path.exists(p2_path)
    ok = core.remove_photo(p2["id"])
    assert ok is True
    assert not os.path.exists(p2_path)  # キャッシュファイルも削除されていること
    assert len(core.get_photos()) == 2

    # 全削除
    core.clear_photos()
    assert len(core.get_photos()) == 0


def test_get_slideshow_images(core_instance):
    """4. get_slideshow_images が写真プールから取得するテスト"""
    core = core_instance

    p1 = core.add_image_bytes(create_dummy_png_bytes(color="red"), original_filename="s1.png")
    p2 = core.add_image_bytes(create_dummy_png_bytes(color="yellow"), original_filename="s2.png")

    images = core.get_slideshow_images()
    assert len(images) == 2
    assert os.path.abspath(p1["path"]) in images
    assert os.path.abspath(p2["path"]) in images


def test_standby_notice_banner(core_instance):
    """5. 写真0枚時の待機画面案内バー合成テスト"""
    core = core_instance

    notice = "📷 スライドショー写真が未登録です（Webリモコンから写真をアップロードできます）"
    core.generate_standby_image(notice_text=notice)

    assert os.path.exists(STANDBY_IMAGE_PATH)
    # 生成された画像が破損なく開けること
    with Image.open(STANDBY_IMAGE_PATH) as img:
        assert img.size == (1920, 1080)


def test_status_dict_playback_modes(core_instance):
    """6. get_status_dict / get_status_data の返却構造テスト"""
    core = core_instance

    p1 = core.add_image_bytes(create_dummy_png_bytes(color="purple"), original_filename="status_pic.png")
    core.set_playback_mode("slideshow")

    status = core.get_status_data()
    assert status["playback_mode"] == "slideshow"
    assert status["photo_count"] == 1
    assert len(status["photos"]) == 1
    assert status["photos"][0]["id"] == p1["id"]
