import os
import shutil
import tempfile
import pytest
from PIL import Image
from streamer_core import StreamerCore, STANDBY_IMAGE_PATH, DEFAULT_STANDBY_IMAGE_PATH

@pytest.fixture
def core_instance():
    core = StreamerCore(override_enable_tunnel=False)
    core.is_running = False  # テスト用にバックグラウンドスレッドを立ち上げない
    yield core

def test_default_standby_asset_exists():
    assert os.path.exists(DEFAULT_STANDBY_IMAGE_PATH), f"{DEFAULT_STANDBY_IMAGE_PATH} must exist"
    with Image.open(DEFAULT_STANDBY_IMAGE_PATH) as img:
        assert img.size[0] > 0 and img.size[1] > 0

def test_generate_standby_default_image(core_instance):
    core_instance.config["standby_mode"] = "image"
    core_instance.config["standby_image_path"] = ""
    core_instance.generate_standby_image()

    assert os.path.exists(STANDBY_IMAGE_PATH)
    with Image.open(STANDBY_IMAGE_PATH) as img:
        assert img.size == (1920, 1080)
        assert img.mode == "RGB"

def test_generate_standby_custom_image(core_instance, tmp_path):
    custom_img_path = str(tmp_path / "custom_test.png")
    test_img = Image.new("RGB", (800, 600), color=(255, 0, 128))
    test_img.save(custom_img_path)

    core_instance.set_standby_config(mode="image", image_path=custom_img_path)
    assert core_instance.config["standby_mode"] == "image"
    assert core_instance.config["standby_image_path"] == custom_img_path

    assert os.path.exists(STANDBY_IMAGE_PATH)
    with Image.open(STANDBY_IMAGE_PATH) as img:
        assert img.size == (1920, 1080)
        center_color = img.getpixel((960, 540))
        assert center_color == (255, 0, 128)

def test_generate_standby_qr_mode(core_instance):
    core_instance.set_standby_config(mode="qr")
    assert core_instance.config["standby_mode"] == "qr"

    assert os.path.exists(STANDBY_IMAGE_PATH)
    with Image.open(STANDBY_IMAGE_PATH) as img:
        assert img.size == (1920, 1080)

def test_status_contains_standby_config(core_instance):
    status = core_instance.get_status_data()
    assert "standby_mode" in status
    assert "standby_image_path" in status
    assert status["standby_mode"] in ("image", "qr")
