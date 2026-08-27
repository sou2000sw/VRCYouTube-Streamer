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


def test_generate_standby_image_mode_with_qr_overlay(core_instance):
    """standby_mode='image' + overlay_qr_enabled=True で QR がデフォルト画像上に合成されること"""
    core_instance.config["standby_mode"] = "image"
    core_instance.config["standby_image_path"] = ""
    core_instance.config["overlay_qr_enabled"] = True
    core_instance.config["overlay_qr_mode"] = "bottom-right"
    core_instance.generate_standby_image()

    assert os.path.exists(STANDBY_IMAGE_PATH)
    with Image.open(STANDBY_IMAGE_PATH) as img:
        assert img.size == (1920, 1080)
        assert img.mode == "RGB"
        # 右下にQRカードが合成されているため、右下コーナー付近は白(カード背景)であるべき
        br_color = img.getpixel((1920 - 50, 1080 - 50))
        # QRカードの白背景 (245前後の高輝度)
        assert br_color[0] > 200 and br_color[1] > 200 and br_color[2] > 200, \
            f"Expected bright pixel at bottom-right (QR card), got {br_color}"


def test_generate_standby_custom_image_with_qr(core_instance, tmp_path):
    """カスタム画像 + overlay_qr_enabled=True で QR が合成されること"""
    custom_img_path = str(tmp_path / "custom_qr_test.png")
    # 単色の暗い画像を作成
    test_img = Image.new("RGB", (1920, 1080), color=(10, 10, 10))
    test_img.save(custom_img_path)

    core_instance.config["standby_mode"] = "image"
    core_instance.config["standby_image_path"] = custom_img_path
    core_instance.config["overlay_qr_enabled"] = True
    core_instance.config["overlay_qr_mode"] = "bottom-right"
    core_instance.generate_standby_image()

    assert os.path.exists(STANDBY_IMAGE_PATH)
    with Image.open(STANDBY_IMAGE_PATH) as img:
        assert img.size == (1920, 1080)
        # 中央は元の暗い色のまま
        center_color = img.getpixel((960, 540))
        assert center_color[0] < 50, f"Center should remain dark, got {center_color}"
        # 右下にQRカードが合成されているため白い
        br_color = img.getpixel((1920 - 50, 1080 - 50))
        assert br_color[0] > 200, f"Bottom-right should be bright (QR card), got {br_color}"
