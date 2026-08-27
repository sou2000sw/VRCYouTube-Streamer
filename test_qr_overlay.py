"""QRオーバーレイ フィルタビルダー & ラジオQR対応のユニットテスト"""
import os
import pytest
from streamer_core import StreamerCore, QR_OVERLAY_PATH


@pytest.fixture
def core_instance():
    core = StreamerCore(override_enable_tunnel=False)
    core.is_running = False
    yield core


# ============================================================
# _build_video_filter_complex() — フィルタビルダーのテスト
# ============================================================

class TestBuildVideoFilterComplex:
    """動画/ラジオ共通の -filter_complex ビルダーのパターン網羅テスト"""

    CLOCK = "drawtext=fontfile='arial.ttf':text='LIVE':fontsize=28:fontcolor=white:x=0:y=0"

    def test_qr_compact_with_clock(self, core_instance):
        result = core_instance._build_video_filter_complex(
            has_qr=True, has_clock=True, qr_idx=2, qr_mode="bottom-right", clock_filter=self.CLOCK
        )
        assert "[0:v][2:v]overlay=" in result
        assert "main_w-overlay_w-25" in result
        assert "[v_qr]" in result
        assert "[vout]" in result
        assert "drawtext=" in result

    def test_qr_compact_no_clock(self, core_instance):
        result = core_instance._build_video_filter_complex(
            has_qr=True, has_clock=False, qr_idx=2, qr_mode="bottom-right", clock_filter=self.CLOCK
        )
        assert "[0:v][2:v]overlay=" in result
        assert result.endswith("[vout]")
        assert "[v_qr]" not in result  # 時計なしなら直接 [vout]

    def test_qr_fullscreen_with_clock(self, core_instance):
        result = core_instance._build_video_filter_complex(
            has_qr=True, has_clock=True, qr_idx=2, qr_mode="fullscreen", clock_filter=self.CLOCK
        )
        assert "scale2ref" in result
        assert "[2:v][0:v]" in result
        assert "overlay=0:0" in result
        assert "[v_qr]" in result
        assert "[vout]" in result

    def test_qr_fullscreen_no_clock(self, core_instance):
        result = core_instance._build_video_filter_complex(
            has_qr=True, has_clock=False, qr_idx=2, qr_mode="fullscreen", clock_filter=self.CLOCK
        )
        assert "scale2ref" in result
        assert result.endswith("[vout]")

    def test_clock_only(self, core_instance):
        result = core_instance._build_video_filter_complex(
            has_qr=False, has_clock=True, qr_idx=0, qr_mode="bottom-right", clock_filter=self.CLOCK
        )
        assert result == f"[0:v]{self.CLOCK}[vout]"

    def test_neither(self, core_instance):
        result = core_instance._build_video_filter_complex(
            has_qr=False, has_clock=False, qr_idx=0, qr_mode="bottom-right", clock_filter=self.CLOCK
        )
        assert result is None

    def test_qr_idx_varies_with_audio(self, core_instance):
        """音声分離ストリーム時 qr_idx=2、映像のみ時 qr_idx=1"""
        r1 = core_instance._build_video_filter_complex(
            has_qr=True, has_clock=False, qr_idx=2, qr_mode="bottom-right", clock_filter=self.CLOCK
        )
        r2 = core_instance._build_video_filter_complex(
            has_qr=True, has_clock=False, qr_idx=1, qr_mode="bottom-right", clock_filter=self.CLOCK
        )
        assert "[2:v]" in r1
        assert "[1:v]" in r2
        assert "[2:v]" not in r2


# ============================================================
# generate_qr_overlay_image() — QRオーバーレイ画像生成のテスト
# ============================================================

class TestGenerateQrOverlayImage:
    def test_compact_mode(self, core_instance):
        core_instance.config["overlay_qr_mode"] = "bottom-right"
        result = core_instance.generate_qr_overlay_image()
        assert result is not None
        assert os.path.exists(result)
        from PIL import Image
        with Image.open(result) as img:
            assert img.mode == "RGBA"
            # コンパクトモードは小さいカード
            assert img.size[0] < 1920
            assert img.size[1] < 1080

    def test_fullscreen_mode(self, core_instance):
        core_instance.config["overlay_qr_mode"] = "fullscreen"
        result = core_instance.generate_qr_overlay_image()
        assert result is not None
        assert os.path.exists(result)
        from PIL import Image
        with Image.open(result) as img:
            assert img.mode == "RGBA"
            assert img.size == (1920, 1080)
