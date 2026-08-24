import os
import sys
import time
import io
import argparse
import signal
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
import qrcode
from PIL import Image

from streamer_core import StreamerCore, CLOUDFLARED_EXE, log_print
from api_server import APIServer

# PyInstallerの --noconsole 対策: sys.stdout / sys.stderr が None になる場合のダミーライター
class DummyWriter:
    def write(self, s):
        pass
    def flush(self):
        pass

if sys.platform == "win32":
    if sys.stdout is not None:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass
    else:
        sys.stdout = DummyWriter()
        
    if sys.stderr is not None:
        try:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass
    else:
        sys.stderr = DummyWriter()

# 設定ウィンドウ
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, streamer_core):
        super().__init__(parent)
        self.streamer_core = streamer_core

        self.title("Settings & API Reference / 設定・API仕様")
        self.geometry("520x660")
        self.minsize(480, 520)

        # 最前面表示とモーダル化
        self.transient(parent)
        self.grab_set()

        # スクロール可能なメインコンテナ
        self.scroll_container = ctk.CTkScrollableFrame(self)
        self.scroll_container.pack(fill="both", expand=True, padx=15, pady=(10, 5))

        # タイトル
        title_lbl = ctk.CTkLabel(self.scroll_container, text="Streaming & Server Settings", font=ctk.CTkFont(size=16, weight="bold"))
        title_lbl.pack(pady=(5, 10))

        # 設定フォームフレーム
        form_frame = ctk.CTkFrame(self.scroll_container)
        form_frame.pack(fill="x", padx=10, pady=(0, 10))

        cfg = self.streamer_core.config

        # 1. サーバーポート
        self.lbl_port = ctk.CTkLabel(form_frame, text="Server Port (サーバーポート):", anchor="w")
        self.lbl_port.pack(fill="x", padx=15, pady=(10, 0))
        self.entry_port = ctk.CTkEntry(form_frame)
        self.entry_port.insert(0, str(cfg.get("port", 8000)))
        self.entry_port.pack(fill="x", padx=15, pady=(2, 8))

        # 2. HLSセグメント秒数 (バッファリング秒数)
        self.lbl_seg = ctk.CTkLabel(form_frame, text="HLS Segment Duration [sec] (セグメント秒数):", anchor="w")
        self.lbl_seg.pack(fill="x", padx=15, pady=(2, 0))
        self.entry_seg = ctk.CTkEntry(form_frame)
        self.entry_seg.insert(0, str(cfg.get("hls_segment_time", 3)))
        self.entry_seg.pack(fill="x", padx=15, pady=(2, 8))

        # 3. 写真スライドショー表示秒数
        self.lbl_photo_dur = ctk.CTkLabel(form_frame, text="Photo Display Duration [sec] (写真表示秒数):", anchor="w")
        self.lbl_photo_dur.pack(fill="x", padx=15, pady=(2, 0))
        self.entry_photo_dur = ctk.CTkEntry(form_frame)
        self.entry_photo_dur.insert(0, str(cfg.get("image_display_duration", 15)))
        self.entry_photo_dur.pack(fill="x", padx=15, pady=(2, 8))

        # 4. 動画切り替わり時の待機秒数
        self.lbl_wait = ctk.CTkLabel(form_frame, text="Transition Wait Duration [sec] (動画切替待機秒数):", anchor="w")
        self.lbl_wait.pack(fill="x", padx=15, pady=(2, 0))
        self.entry_wait = ctk.CTkEntry(form_frame)
        self.entry_wait.insert(0, str(cfg.get("video_transition_wait_seconds", 5)))
        self.entry_wait.pack(fill="x", padx=15, pady=(2, 8))

        # 5. プレイヤーバッファ保持セグメント数 (Live Sync Count)
        self.lbl_sync = ctk.CTkLabel(form_frame, text="Web Player Live Sync Count (再生同期バッファ数):", anchor="w")
        self.lbl_sync.pack(fill="x", padx=15, pady=(2, 0))
        self.entry_sync = ctk.CTkEntry(form_frame)
        self.entry_sync.insert(0, str(cfg.get("live_sync_duration_count", 4)))
        self.entry_sync.pack(fill="x", padx=15, pady=(2, 10))

        # 6. ループ再生 & シャッフル再生のデフォルト設定
        self.switch_loop = ctk.CTkSwitch(form_frame, text="🔁 Loop Queue (キュー保持・繰り返し再生)")
        if cfg.get("loop_queue", False):
            self.switch_loop.select()
        self.switch_loop.pack(anchor="w", padx=15, pady=(4, 6))

        self.switch_shuffle = ctk.CTkSwitch(form_frame, text="🔀 Shuffle Play (シャッフル再生モード)")
        if cfg.get("shuffle", False):
            self.switch_shuffle.select()
        self.switch_shuffle.pack(anchor="w", padx=15, pady=(2, 6))

        self.switch_photo_advance = ctk.CTkSwitch(form_frame, text="⏱ Auto Advance Photos (写真の自動送り)")
        if cfg.get("image_auto_advance", False):
            self.switch_photo_advance.select()
        self.switch_photo_advance.pack(anchor="w", padx=15, pady=(2, 6))

        # 6.5. BGM / ラジオモード設定 (音声のみ + 静止画低帯域配信)
        self.switch_radio = ctk.CTkSwitch(form_frame, text="📻 Radio / BGM Mode (YouTube音声のみ+静止画・超低帯域配信)")
        if cfg.get("radio_mode", False):
            self.switch_radio.select()
        self.switch_radio.pack(anchor="w", padx=15, pady=(4, 4))

        self.lbl_radio_bg = ctk.CTkLabel(form_frame, text="📻 Radio Background (ラジオモード時の背景):", anchor="w")
        self.lbl_radio_bg.pack(fill="x", padx=15, pady=(2, 2))

        curr_radio_bg = cfg.get("radio_bg_source", "card")
        if curr_radio_bg == "slideshow":
            radio_bg_val = "Slideshow (写真スライドショー)"
        elif curr_radio_bg == "standby":
            radio_bg_val = "Standby (待機画面・QR)"
        else:
            radio_bg_val = "Card (サムネイル＆楽曲情報)"

        self.seg_radio_bg = ctk.CTkSegmentedButton(
            form_frame,
            values=["Card (サムネイル＆楽曲情報)", "Standby (待機画面・QR)", "Slideshow (写真スライドショー)"]
        )
        self.seg_radio_bg.set(radio_bg_val)
        self.seg_radio_bg.pack(fill="x", padx=15, pady=(2, 4))

        self.lbl_radio_info = ctk.CTkLabel(
            form_frame,
            text="💡 ラジオモード時は動画を落とさず帯域を約300kbps（通常比90%減）に極小化し、VRChatでのバッファ詰まりを防止します。",
            font=ctk.CTkFont(size=11),
            text_color="#34D399",
            anchor="w",
            wraplength=440,
            justify="left"
        )
        self.lbl_radio_info.pack(fill="x", padx=15, pady=(0, 8))

        # 7. QRコード上書き表示 (ウォーターマーク) 設定
        is_qr_on = bool(cfg.get("overlay_qr_enabled", False) or cfg.get("overlay_qr_video", False) or cfg.get("overlay_qr_image", False))
        self.switch_qr_overlay = ctk.CTkSwitch(form_frame, text="🔲 QR Overlay (動画・写真にQR・URL上書き表示)")
        if is_qr_on:
            self.switch_qr_overlay.select()
        self.switch_qr_overlay.pack(anchor="w", padx=15, pady=(2, 6))

        self.lbl_qr_mode = ctk.CTkLabel(form_frame, text="📐 Overlay Layout (表示レイアウト):", anchor="w")
        self.lbl_qr_mode.pack(fill="x", padx=15, pady=(4, 2))

        curr_mode = cfg.get("overlay_qr_mode", "bottom-right")
        mode_val = "Fullscreen (フル画面)" if curr_mode == "fullscreen" else "Compact (右下に小さく)"
        self.seg_qr_mode = ctk.CTkSegmentedButton(form_frame, values=["Compact (右下に小さく)", "Fullscreen (フル画面)"])
        self.seg_qr_mode.set(mode_val)
        self.seg_qr_mode.pack(fill="x", padx=15, pady=(2, 4))

        self.lbl_qr_warn = ctk.CTkLabel(
            form_frame,
            text="⚠️ 注意: 動画オーバーレイ有効時はリアルタイム再エンコード処理のためバッファ（読み込み待ち）が発生しやすくなります。",
            font=ctk.CTkFont(size=11),
            text_color="#F59E0B",
            anchor="w",
            wraplength=440,
            justify="left"
        )
        self.lbl_qr_warn.pack(fill="x", padx=15, pady=(0, 8))

        # 8. Cloudflare トンネル起動設定
        self.switch_tunnel = ctk.CTkSwitch(form_frame, text="🌐 Enable Cloudflare Tunnel (トンネル自動起動)")
        if cfg.get("enable_tunnel", True):
            self.switch_tunnel.select()
        self.switch_tunnel.pack(anchor="w", padx=15, pady=(2, 10))

        # 9. Webリモコン (外部ブラウザ/スマホ) 権限設定
        self.lbl_web_perms = ctk.CTkLabel(form_frame, text="📱 Web Remote Permissions (ブラウザ操作権限):", font=ctk.CTkFont(weight="bold"), anchor="w")
        self.lbl_web_perms.pack(fill="x", padx=15, pady=(8, 4))

        self.switch_web_add = ctk.CTkSwitch(form_frame, text="Allow Adding Media (スマホからの動画・写真追加を許可)")
        if cfg.get("allow_web_queue_add", True):
            self.switch_web_add.select()
        self.switch_web_add.pack(anchor="w", padx=15, pady=(2, 4))

        self.switch_web_edit = ctk.CTkSwitch(form_frame, text="Allow Queue Edit (キューの削除・並び替えを許可)")
        if cfg.get("allow_web_queue_edit", True):
            self.switch_web_edit.select()
        self.switch_web_edit.pack(anchor="w", padx=15, pady=(2, 4))

        self.switch_web_control = ctk.CTkSwitch(form_frame, text="Allow Playback Control (スキップ・ループ等の操作を許可)")
        if cfg.get("allow_web_playback_control", True):
            self.switch_web_control.select()
        self.switch_web_control.pack(anchor="w", padx=15, pady=(2, 12))

        # --- 折りたたみ式 API リファレンス ---
        self.api_toggle_btn = ctk.CTkButton(
            self.scroll_container,
            text="▶ API 仕様・引数リファレンス (表示 / 折りたたみ)",
            fg_color="#34495E",
            hover_color="#2C3E50",
            anchor="w",
            command=self.toggle_api_ref
        )
        self.api_toggle_btn.pack(fill="x", padx=10, pady=(5, 5))

        self.api_ref_frame = ctk.CTkFrame(self.scroll_container)
        self.is_api_ref_open = False

        api_doc_text = """【起動コマンド引数 (CLI)】
  --headless / -hl       : GUIを表示せずAPIサーバーとして起動
  --no-tunnel / -nt      : Cloudflareトンネルを起動しない（ローカルテストモード）
  --port / -p <ポート>   : サーバーポート番号 (デフォルト: 8000)
  --host <アドレス>      : ホストアドレス (デフォルト: 127.0.0.1)

【HTTP API エンドポイント (JSON)】
すべてのAPIは CORS (Access-Control-Allow-Origin: *) に対応。

■ GET /api/status
  ストリーマーの接続状況、配信中動画、キューの状態、ループ/シャッフル状態を取得。
  レスポンス例:
  {
    "status": "streaming",  // offline / buffering / streaming / finishing / error
    "status_detail": "Active (Streaming)",
    "tunnel_url": "https://xxxx.trycloudflare.com",
    "stream_url": "https://xxxx.trycloudflare.com/stream.m3u8",
    "current_video": { "title": "...", "url": "...", "duration": 213 },
    "queue": [ { "title": "...", "url": "..." } ],
    "loop_queue": true,
    "shuffle": false
  }

■ POST /api/queue
  キューに動画・プレイリスト・画像URLを追加。
  リクエスト例:
  {
    "url": "https://www.youtube.com/watch?v=..."
  }

■ POST /api/upload
  写真・画像バイナリをアップロードしてキューに追加 (multipart/form-data または image/*)。

■ POST /api/control
  再生およびキューの操作。
  リクエスト例:
  - スキップ (次へ):      { "action": "skip" }
  - 前へ戻る (Prev):      { "action": "prev" }
  - 写真一時停止トグル:   { "action": "toggle_image_pause" }
  - 写真表示秒数変更:     { "action": "set_image_duration", "duration": 15 }
  - キュー全消去:         { "action": "clear_queue" }
  - 停止＆キュー消去:     { "action": "stop" }
  - キュー即時シャッフル: { "action": "shuffle" }
  - ラジオ/BGMモード切替: { "action": "set_radio_mode", "enabled": true }
  - ラジオ背景ソース切替: { "action": "set_radio_bg_source", "source": "card" }  // card / standby / slideshow
  - ループ再生の切替:     { "action": "set_loop", "enabled": true }
  - シャッフル再生の切替: { "action": "set_shuffle", "enabled": true }
  - 指定動画の削除:       { "action": "delete_item", "index": 0 }
  - 動画の並べ替え:       { "action": "move_item", "from_index": 0, "to_index": 1 }

■ POST /api/shutdown
  サーバーおよび関連プロセスを安全に終了。

■ GET /api/config
  現在の設定JSONを取得。

■ POST /api/config
  設定JSONを更新・保存 (例: {"loop_queue": true, "shuffle": true, "radio_mode": true, "radio_bg_source": "card", "image_display_duration": 15})
"""
        self.api_textbox = ctk.CTkTextbox(self.api_ref_frame, height=260, font=ctk.CTkFont(family="Consolas", size=11))
        self.api_textbox.insert("1.0", api_doc_text)
        self.api_textbox.configure(state="disabled")
        self.api_textbox.pack(fill="both", expand=True, padx=10, pady=10)

        # 画面下部ボタンフレーム
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(5, 12))

        self.btn_save = ctk.CTkButton(btn_frame, text="Save / 保存", fg_color="#2ECC71", hover_color="#27AE60", command=self.save_settings)
        self.btn_save.pack(side="right", padx=(10, 0))

        self.btn_cancel = ctk.CTkButton(btn_frame, text="Cancel / キャンセル", fg_color="#7F8C8D", hover_color="#707B7C", command=self.destroy)
        self.btn_cancel.pack(side="right")

    def toggle_api_ref(self):
        if self.is_api_ref_open:
            self.api_ref_frame.pack_forget()
            self.api_toggle_btn.configure(text="▶ API 仕様・引数リファレンス (表示 / 折りたたみ)")
            self.is_api_ref_open = False
        else:
            self.api_ref_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self.api_toggle_btn.configure(text="▼ API 仕様・引数リファレンス (表示 / 折りたたみ)")
            self.is_api_ref_open = True

    def save_settings(self):
        try:
            port = int(self.entry_port.get().strip())
            seg_time = int(self.entry_seg.get().strip())
            photo_dur = int(self.entry_photo_dur.get().strip())
            wait_time = int(self.entry_wait.get().strip())
            sync_count = int(self.entry_sync.get().strip())
            loop_queue = bool(self.switch_loop.get())
            shuffle = bool(self.switch_shuffle.get())
            photo_advance = bool(self.switch_photo_advance.get())
            radio_mode = bool(self.switch_radio.get())
            
            selected_bg = self.seg_radio_bg.get()
            if "Slideshow" in selected_bg:
                radio_bg = "slideshow"
            elif "Standby" in selected_bg:
                radio_bg = "standby"
            else:
                radio_bg = "card"

            if port <= 0 or port > 65535:
                raise ValueError("Port must be between 1 and 65535.")
            if seg_time <= 0 or photo_dur <= 0 or wait_time < 0 or sync_count <= 0:
                raise ValueError("Durations and counts must be positive integers.")

            old_port = self.streamer_core.config.get("port", 8000)

            qr_mode = "fullscreen" if "Fullscreen" in self.seg_qr_mode.get() else "bottom-right"
            qr_enabled = bool(self.switch_qr_overlay.get())

            new_cfg = {
                "port": port,
                "hls_segment_time": seg_time,
                "image_display_duration": photo_dur,
                "image_auto_advance": photo_advance,
                "radio_mode": radio_mode,
                "radio_bg_source": radio_bg,
                "overlay_qr_enabled": qr_enabled,
                "overlay_qr_video": qr_enabled,
                "overlay_qr_image": qr_enabled,
                "overlay_qr_mode": qr_mode,
                "enable_tunnel": bool(self.switch_tunnel.get()),
                "video_transition_wait_seconds": wait_time,
                "live_sync_duration_count": sync_count,
                "loop_queue": loop_queue,
                "shuffle": shuffle,
                "allow_web_queue_add": bool(self.switch_web_add.get()),
                "allow_web_queue_edit": bool(self.switch_web_edit.get()),
                "allow_web_playback_control": bool(self.switch_web_control.get())
            }

            self.streamer_core.save_config(new_cfg)
            
            if port != old_port:
                messagebox.showinfo("Saved", "Settings saved successfully!\nNote: Port change will take effect on next restart.")
            else:
                messagebox.showinfo("Saved", "Settings saved and applied successfully!")
            
            self.destroy()
        except Exception as e:
            messagebox.showerror("Invalid Input", f"Please check your input values:\n{e}")

# QRコード表示ダイアログ
class QRCodeWindow(ctk.CTkToplevel):
    def __init__(self, parent, url):
        super().__init__(parent)
        self.title("📱 Share QR Code / スマホ共有用QRコード")
        self.geometry("380x440")
        self.resizable(False, False)
        self.transient(parent)

        title_lbl = ctk.CTkLabel(self, text="📱 スマホで読み取って動画を追加", font=ctk.CTkFont(size=15, weight="bold"))
        title_lbl.pack(pady=(15, 5))

        sub_lbl = ctk.CTkLabel(self, text="カメラでQRコードを読み取ると、\nスマホのブラウザから直接動画をキューに追加できます。", font=ctk.CTkFont(size=12), text_color="gray")
        sub_lbl.pack(pady=(0, 8))

        # QRコード生成
        qr_img = self.generate_qr_image(url)
        if qr_img:
            ctk_img = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(220, 220))
            qr_label = ctk.CTkLabel(self, image=ctk_img, text="")
            qr_label.pack(pady=5)

        url_entry = ctk.CTkEntry(self, width=320)
        url_entry.insert(0, url)
        url_entry.configure(state="readonly")
        url_entry.pack(pady=(8, 5))

        close_btn = ctk.CTkButton(self, text="Close / 閉じる", width=120, command=self.destroy)
        close_btn.pack(pady=10)

    def generate_qr_image(self, url):
        try:
            qr = qrcode.QRCode(version=1, box_size=8, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            return qr.make_image(fill_color="black", back_color="white").convert("RGB")
        except Exception:
            return None

# メインGUIアプリケーション定義
class App(ctk.CTk):
    def __init__(self, streamer_core, api_server):
        super().__init__()
        self.streamer_core = streamer_core
        self.api_server = api_server

        self.title("VRChat YouTube HLS Streamer")
        self.geometry("680x620")
        self.minsize(540, 480)

        # ウィンドウの✕ボタンでも on_closing() を通す。
        # これが無いと shutdown() が呼ばれず、cloudflared / ffmpeg の子プロセスが孤児化する。
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # テーマと配色の設定
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # 1. Header Frame (Title + Settings button)
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=20, pady=(10, 5))

        self.title_label = ctk.CTkLabel(self.header_frame, text="VRC YouTube Streamer", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(side="left")

        self.settings_btn = ctk.CTkButton(self.header_frame, text="⚙ Settings", width=90, fg_color="#34495E", hover_color="#2C3E50", command=self.open_settings)
        self.settings_btn.pack(side="right")

        self.radio_switch = ctk.CTkSwitch(
            self.header_frame,
            text="📻 Radio/BGM",
            width=110,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.toggle_radio_mode
        )
        if self.streamer_core.config.get("radio_mode", False):
            self.radio_switch.select()
        self.radio_switch.pack(side="right", padx=(0, 12))

        # 2. Status Frame (Stream Status, Now Playing & Tunnel URL)
        self.status_frame = ctk.CTkFrame(self)
        self.status_frame.pack(fill="x", padx=20, pady=5)

        self.stream_status_title = ctk.CTkLabel(self.status_frame, text="Stream Status:", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray")
        self.stream_status_title.pack(anchor="w", padx=15, pady=(8, 2))

        self.stream_status_label = ctk.CTkLabel(self.status_frame, text="Offline (Queue Empty)", font=ctk.CTkFont(size=14, weight="bold"), anchor="w", text_color="#E74C3C")
        self.stream_status_label.pack(fill="x", anchor="w", padx=15, pady=(0, 4))

        self.now_playing_title = ctk.CTkLabel(self.status_frame, text="Now Playing:", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray")
        self.now_playing_title.pack(anchor="w", padx=15, pady=(4, 2))

        self.now_playing_label = ctk.CTkLabel(self.status_frame, text="None", font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
        self.now_playing_label.pack(fill="x", anchor="w", padx=15, pady=(0, 8))

        self.tunnel_title = ctk.CTkLabel(self.status_frame, text="HLS URL for VRChat:", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray")
        self.tunnel_title.pack(anchor="w", padx=15, pady=(0, 2))

        self.url_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        self.url_frame.pack(fill="x", padx=15, pady=(0, 8))

        self.tunnel_label = ctk.CTkLabel(self.url_frame, text="Starting tunnel...", font=ctk.CTkFont(size=12), anchor="w")
        self.tunnel_label.pack(side="left", fill="x", expand=True)

        self.qr_btn = ctk.CTkButton(self.url_frame, text="📱 QR Code", width=85, fg_color="#2E4053", hover_color="#1F2A36", command=self.open_qr_code)
        self.qr_btn.pack(side="right", padx=(5, 0))

        self.copy_btn = ctk.CTkButton(self.url_frame, text="Copy URL", width=80, command=self.copy_url)
        self.copy_btn.pack(side="right", padx=(10, 0))

        # 3. Add to Queue Frame
        self.add_frame = ctk.CTkFrame(self)
        self.add_frame.pack(fill="x", padx=20, pady=5)

        self.url_entry = ctk.CTkEntry(self.add_frame, placeholder_text="Paste YouTube URL / Photo URL here...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(10, 5), pady=10)
        self.url_entry.bind("<Return>", lambda e: self.add_to_queue())

        self.add_btn = ctk.CTkButton(self.add_frame, text="Add Video", width=85, command=self.add_to_queue)
        self.add_btn.pack(side="right", padx=(5, 10), pady=10)

        self.add_photo_btn = ctk.CTkButton(self.add_frame, text="🖼 Add Photo", width=95, fg_color="#2E4053", hover_color="#1F2A36", command=self.add_photo_file)
        self.add_photo_btn.pack(side="right", padx=(0, 5), pady=10)

        # 5. Bottom Control Frame
        self.control_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.control_frame.pack(side="bottom", fill="x", padx=20, pady=(4, 12))

        self.skip_btn = ctk.CTkButton(self.control_frame, text="⏭ Skip", width=75, fg_color="#E74C3C", hover_color="#C0392B", command=self.streamer_core.skip)
        self.skip_btn.pack(side="left", padx=(0, 8))

        self.clear_btn = ctk.CTkButton(self.control_frame, text="Clear Queue", fg_color="#7F8C8D", hover_color="#707B7C", command=self.clear_queue)
        self.clear_btn.pack(side="left")

        self.exit_btn = ctk.CTkButton(self.control_frame, text="Exit", fg_color="#34495E", hover_color="#2C3E50", command=self.on_closing)
        self.exit_btn.pack(side="right")

        # 4.5. Photo Slideshow Control Bar (メイン画面で直接操作可能)
        self.photo_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.photo_bar.pack(side="bottom", fill="x", padx=20, pady=(2, 2))

        self.lbl_photo_bar = ctk.CTkLabel(self.photo_bar, text="🖼 Photo Slideshow:", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray")
        self.lbl_photo_bar.pack(side="left", padx=(0, 8))

        self.photo_advance_switch = ctk.CTkSwitch(self.photo_bar, text="⏱ Auto Advance", font=ctk.CTkFont(size=11), command=self.toggle_photo_advance)
        if self.streamer_core.config.get("image_auto_advance", False):
            self.photo_advance_switch.select()
        self.photo_advance_switch.pack(side="left", padx=(0, 12))

        self.lbl_duration = ctk.CTkLabel(self.photo_bar, text="Duration:", font=ctk.CTkFont(size=11), text_color="gray")
        self.lbl_duration.pack(side="left", padx=(0, 4))

        self.duration_combo = ctk.CTkOptionMenu(
            self.photo_bar,
            values=["5s", "10s", "15s", "20s", "30s", "60s", "120s"],
            width=75,
            height=22,
            font=ctk.CTkFont(size=11),
            command=self.on_change_photo_duration
        )
        curr_dur = str(self.streamer_core.config.get("image_display_duration", 15)) + "s"
        self.duration_combo.set(curr_dur if curr_dur in ["5s", "10s", "15s", "20s", "30s", "60s", "120s"] else "15s")
        self.duration_combo.pack(side="left")

        # 4. Queue List Frame
        self.queue_frame = ctk.CTkFrame(self)
        self.queue_frame.pack(fill="both", expand=True, padx=20, pady=5)

        # Queue List Header (Title + Shuffle & Loop Controls)
        self.queue_header = ctk.CTkFrame(self.queue_frame, fg_color="transparent")
        self.queue_header.pack(fill="x", padx=15, pady=(5, 2))

        self.queue_title = ctk.CTkLabel(self.queue_header, text="Play Queue (0 items)", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray")
        self.queue_title.pack(side="left")

        self.loop_switch = ctk.CTkSwitch(self.queue_header, text="🔁 Loop", width=70, font=ctk.CTkFont(size=11), command=self.toggle_loop)
        if self.streamer_core.config.get("loop_queue", False):
            self.loop_switch.select()
        self.loop_switch.pack(side="right", padx=(6, 0))

        self.shuffle_switch = ctk.CTkSwitch(self.queue_header, text="🔀 Shuffle", width=80, font=ctk.CTkFont(size=11), command=self.toggle_shuffle)
        if self.streamer_core.config.get("shuffle", False):
            self.shuffle_switch.select()
        self.shuffle_switch.pack(side="right", padx=(6, 0))

        self.shuffle_btn = ctk.CTkButton(self.queue_header, text="🔀 Shuffle List", width=85, height=22, font=ctk.CTkFont(size=11), fg_color="#34495E", hover_color="#2C3E50", command=self.shuffle_now)
        self.shuffle_btn.pack(side="right", padx=(0, 6))

        self.queue_scroll = ctk.CTkScrollableFrame(self.queue_frame, fg_color="transparent")
        self.queue_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.last_queue_titles = None

        # ドラッグ＆ドロップおよび自動スクロール状態管理
        self.dragged_idx = None
        self.drag_target_idx = None
        self.queue_item_widgets = []
        self.auto_scroll_speed = 0
        self.auto_scroll_active = False
        self.last_drag_y_root = 0

        # UI更新定期ループ開始
        self.update_ui_loop()

    def on_drag_start(self, event, idx):
        self.dragged_idx = idx
        self.drag_target_idx = idx
        self.auto_scroll_speed = 0
        self.last_drag_y_root = event.y_root
        # ドラッグ中のアイテムをハイライト
        for item in self.queue_item_widgets:
            if item["index"] == idx:
                item["frame"].configure(fg_color="#1F4068")
            else:
                item["frame"].configure(fg_color="transparent")

    def on_drag_motion(self, event):
        if self.dragged_idx is None or not self.queue_item_widgets:
            return

        self.last_drag_y_root = event.y_root

        # 自動スクロール判定 (上端・下端のしきい値ゾーン)
        try:
            scroll_top = self.queue_scroll.winfo_rooty()
            scroll_height = self.queue_scroll.winfo_height()
            scroll_bottom = scroll_top + scroll_height
            margin = 35

            if event.y_root < scroll_top + margin:
                self.auto_scroll_speed = -2
            elif event.y_root > scroll_bottom - margin:
                self.auto_scroll_speed = 2
            else:
                self.auto_scroll_speed = 0

            if self.auto_scroll_speed != 0 and not self.auto_scroll_active:
                self.auto_scroll_active = True
                self.auto_scroll_step()
        except Exception:
            self.auto_scroll_speed = 0

        self.update_drag_target(event.y_root)

    def update_drag_target(self, y_root):
        if self.dragged_idx is None or not self.queue_item_widgets:
            return

        new_target = self.dragged_idx
        for item in self.queue_item_widgets:
            f = item["frame"]
            try:
                fy = f.winfo_rooty()
                fh = f.winfo_height()
                if fy <= y_root <= fy + fh:
                    new_target = item["index"]
                    break
                elif y_root < fy and item["index"] == 0:
                    new_target = 0
                    break
                elif y_root > fy + fh and item["index"] == len(self.queue_item_widgets) - 1:
                    new_target = len(self.queue_item_widgets) - 1
            except Exception:
                pass

        if new_target != self.drag_target_idx:
            self.drag_target_idx = new_target
            # ターゲット位置の視覚フィードバック
            for item in self.queue_item_widgets:
                idx = item["index"]
                if idx == self.dragged_idx:
                    item["frame"].configure(fg_color="#1F4068")
                elif idx == self.drag_target_idx:
                    item["frame"].configure(fg_color="#162447")
                else:
                    item["frame"].configure(fg_color="transparent")

    def auto_scroll_step(self):
        if self.dragged_idx is None or self.auto_scroll_speed == 0:
            self.auto_scroll_active = False
            return

        try:
            # CTkScrollableFrame の内部 Canvas をスクロール
            if hasattr(self.queue_scroll, "_parent_canvas"):
                self.queue_scroll._parent_canvas.yview_scroll(self.auto_scroll_speed, "units")
            self.update_drag_target(self.last_drag_y_root)
        except Exception:
            pass

        if self.auto_scroll_speed != 0 and self.dragged_idx is not None:
            self.after(40, self.auto_scroll_step)
        else:
            self.auto_scroll_active = False

    def on_drag_end(self, event):
        self.auto_scroll_speed = 0
        self.auto_scroll_active = False
        if self.dragged_idx is not None and self.drag_target_idx is not None:
            if self.dragged_idx != self.drag_target_idx:
                self.streamer_core.move_queue_item(self.dragged_idx, self.drag_target_idx)
        self.dragged_idx = None
        self.drag_target_idx = None
        self.last_queue_titles = None
        self.update_ui_loop()

    def toggle_radio_mode(self):
        val = bool(self.radio_switch.get())
        self.streamer_core.set_radio_mode(val)

    def toggle_loop(self):
        val = bool(self.loop_switch.get())
        self.streamer_core.set_loop(val)

    def toggle_shuffle(self):
        val = bool(self.shuffle_switch.get())
        self.streamer_core.set_shuffle(val)

    def shuffle_now(self):
        self.streamer_core.shuffle_queue()
        self.last_queue_titles = None
        self.update_ui_loop()

    def open_settings(self):
        SettingsWindow(self, self.streamer_core)

    def open_qr_code(self):
        url = self.streamer_core.tunnel_raw_url or self.streamer_core.tunnel_url
        if not url:
            port = self.streamer_core.config.get("port", 8000)
            url = f"http://localhost:{port}"
        QRCodeWindow(self, url)

    def copy_url(self):
        url = self.streamer_core.tunnel_url
        if not url and not getattr(self.streamer_core, "enable_tunnel", True):
            port = self.streamer_core.config.get("port", 8000)
            url = f"http://localhost:{port}/stream.m3u8"
        if url:
            self.clipboard_clear()
            self.clipboard_append(url)
            self.copy_btn.configure(text="Copied!")
            self.after(2000, lambda: self.copy_btn.configure(text="Copy URL"))
        else:
            messagebox.showwarning("Warning", "URL is not ready yet.")

    def toggle_photo_advance(self):
        val = bool(self.photo_advance_switch.get())
        self.streamer_core.set_image_auto_advance(val)

    def on_change_photo_duration(self, val_str):
        try:
            sec = int(val_str.replace("s", "").strip())
            self.streamer_core.set_image_duration(sec)
        except Exception:
            pass

    def add_photo_file(self):
        file_paths = filedialog.askopenfilenames(
            title="Select Photo(s) / Image(s)",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif"),
                ("All Files", "*.*")
            ]
        )
        if not file_paths:
            return

        total = len(file_paths)
        self.add_photo_btn.configure(state="disabled", text=f"Adding (0/{total})...")

        def bg_add():
            added_count = 0
            for i, fp in enumerate(file_paths):
                self.after(0, lambda idx=i+1: self.add_photo_btn.configure(text=f"Adding ({idx}/{total})..."))
                item = self.streamer_core.add_image_file(fp)
                if item:
                    added_count += 1
            log_print(f"[GUI] Added {added_count}/{total} photo(s) to queue.")
            self.last_queue_titles = None
            self.after(0, lambda: self.add_photo_btn.configure(state="normal", text="🖼 Add Photo"))

        threading.Thread(target=bg_add, daemon=True).start()

    def add_to_queue(self):
        url = self.url_entry.get().strip()
        if not url:
            return

        self.url_entry.delete(0, 'end')
        self.add_btn.configure(state="disabled", text="Adding...")

        def bg_add():
            items = self.streamer_core.add_to_queue(url)
            if items:
                log_print(f"Added {len(items)} items to queue.")
                self.last_queue_titles = None
            else:
                log_print("No items added (Failed to parse or empty).")
            self.after(0, lambda: self.add_btn.configure(state="normal", text="Add Video"))

        threading.Thread(target=bg_add, daemon=True).start()

    def clear_queue(self):
        self.streamer_core.clear_queue()
        self.last_queue_titles = None

    def delete_queue_item(self, idx):
        self.streamer_core.delete_queue_item(idx)
        self.last_queue_titles = None

    def move_queue_item_up(self, idx):
        self.streamer_core.move_queue_item(idx, idx - 1)
        self.last_queue_titles = None
        self.update_ui_loop()

    def move_queue_item_down(self, idx):
        self.streamer_core.move_queue_item(idx, idx + 1)
        self.last_queue_titles = None
        self.update_ui_loop()

    def update_ui_loop(self):
        # ドラッグ中は定期更新によるUI再構築を一時スキップ
        if self.dragged_idx is not None:
            if self.streamer_core.is_running:
                self.after(500, self.update_ui_loop)
            return

        # Loop & Shuffle & Radio スイッチの状態同期
        core_loop = bool(self.streamer_core.config.get("loop_queue", False))
        if bool(self.loop_switch.get()) != core_loop:
            if core_loop:
                self.loop_switch.select()
            else:
                self.loop_switch.deselect()

        core_shuffle = bool(self.streamer_core.config.get("shuffle", False))
        if bool(self.shuffle_switch.get()) != core_shuffle:
            if core_shuffle:
                self.shuffle_switch.select()
            else:
                self.shuffle_switch.deselect()

        core_radio = bool(self.streamer_core.config.get("radio_mode", False))
        if bool(self.radio_switch.get()) != core_radio:
            if core_radio:
                self.radio_switch.select()
            else:
                self.radio_switch.deselect()

        # 写真自動送りスイッチ & 表示秒数コンボの状態同期
        core_advance = bool(self.streamer_core.config.get("image_auto_advance", False))
        if bool(self.photo_advance_switch.get()) != core_advance:
            if core_advance:
                self.photo_advance_switch.select()
            else:
                self.photo_advance_switch.deselect()

        core_dur = str(self.streamer_core.config.get("image_display_duration", 15)) + "s"
        if self.duration_combo.get() != core_dur and core_dur in ["5s", "10s", "15s", "20s", "30s", "60s", "120s"]:
            self.duration_combo.set(core_dur)

        # 0. Stream Status
        status_detail = self.streamer_core.status_detail
        self.stream_status_label.configure(text=status_detail)
        status_code = self.streamer_core.status
        if status_code == "streaming":
            self.stream_status_label.configure(text_color="#2ECC71") # Green
        elif status_code == "buffering":
            self.stream_status_label.configure(text_color="#F1C40F") # Yellow
        elif status_code == "finishing":
            self.stream_status_label.configure(text_color="#3498DB") # Blue
        else:
            self.stream_status_label.configure(text_color="#E74C3C") # Red

        # 1. Now Playing
        curr = self.streamer_core.current_video
        title_text = curr.get("title", "None") if curr else "None"
        self.now_playing_label.configure(text=title_text)

        # 2. Tunnel URL
        self.tunnel_label.configure(text=self.streamer_core.tunnel_url or "Starting tunnel...")

        # 3. Queue List
        with self.streamer_core.queue_lock:
            q = self.streamer_core.play_queue
            q_len = len(q)
            self.queue_title.configure(text=f"Play Queue ({q_len} items)")

            current_queue_titles = [item.get("title", "?") for item in q]
            current_url = self.streamer_core.tunnel_raw_url or self.streamer_core.tunnel_url or ""
            last_url = getattr(self, "last_rendered_tunnel_url", "")

            if getattr(self, "last_queue_titles", None) != current_queue_titles or (q_len == 0 and last_url != current_url):
                self.last_queue_titles = current_queue_titles.copy()
                self.last_rendered_tunnel_url = current_url
                self.queue_item_widgets.clear()

                for widget in self.queue_scroll.winfo_children():
                    widget.destroy()

                if q_len == 0:
                    empty_frame = ctk.CTkFrame(self.queue_scroll, fg_color="transparent")
                    empty_frame.pack(fill="both", expand=True, pady=10)

                    title_lbl = ctk.CTkLabel(
                        empty_frame,
                        text="📱 スマホから動画を追加できます (Scan to Request)",
                        font=ctk.CTkFont(size=14, weight="bold"),
                        text_color="#38BDF8"
                    )
                    title_lbl.pack(pady=(5, 4))

                    url = self.streamer_core.tunnel_raw_url or self.streamer_core.tunnel_url
                    if not url:
                        port = self.streamer_core.config.get("port", 8000)
                        url = f"http://localhost:{port}"

                    try:
                        qr = qrcode.QRCode(version=1, box_size=5, border=2)
                        qr.add_data(url)
                        qr.make(fit=True)
                        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
                        ctk_img = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(160, 160))
                        qr_lbl = ctk.CTkLabel(empty_frame, image=ctk_img, text="")
                        qr_lbl.pack(pady=6)
                    except Exception:
                        pass

                    url_lbl = ctk.CTkLabel(
                        empty_frame,
                        text=f"リクエストURL: {url}",
                        font=ctk.CTkFont(size=12, weight="bold"),
                        text_color="#F8FAFC"
                    )
                    url_lbl.pack(pady=(2, 2))

                    hint_lbl = ctk.CTkLabel(
                        empty_frame,
                        text="スマホのカメラでQRコードを読み取るか、上の入力欄からYouTube動画を追加してください。",
                        font=ctk.CTkFont(size=11),
                        text_color="gray"
                    )
                    hint_lbl.pack(pady=(0, 5))
                else:
                    for idx, item in enumerate(q):
                        title = item.get("title", "Unknown")
                        item_frame = ctk.CTkFrame(self.queue_scroll, fg_color="transparent", corner_radius=6)
                        item_frame.pack(fill="x", pady=2)
                        self.queue_item_widgets.append({"frame": item_frame, "index": idx})

                        # ドラッグ用グリップアイコン
                        drag_handle = ctk.CTkLabel(item_frame, text="☰", width=22, font=ctk.CTkFont(size=13),
                                                   text_color="#7F8C8D", cursor="fleur")
                        drag_handle.pack(side="left", padx=(4, 2))

                        # タイトルテキスト
                        title_lbl = ctk.CTkLabel(item_frame, text=f"{idx+1}. {title}", font=ctk.CTkFont(size=12),
                                                 anchor="w", cursor="fleur")
                        title_lbl.pack(side="left", fill="x", expand=True, padx=(2, 5))

                        # ドラッグ＆ドロップイベントのバインド
                        for w in (item_frame, drag_handle, title_lbl):
                            w.bind("<Button-1>", lambda e, idx=idx: self.on_drag_start(e, idx))
                            w.bind("<B1-Motion>", self.on_drag_motion)
                            w.bind("<ButtonRelease-1>", self.on_drag_end)

                        # 並べ替え Up ボタン
                        up_state = "normal" if idx > 0 else "disabled"
                        up_btn = ctk.CTkButton(item_frame, text="▲", width=25, height=20, fg_color="#34495E", hover_color="#2C3E50", state=up_state,
                                               command=lambda idx=idx: self.move_queue_item_up(idx))
                        up_btn.pack(side="left", padx=2)

                        # 並べ替え Down ボタン
                        down_state = "normal" if idx < q_len - 1 else "disabled"
                        down_btn = ctk.CTkButton(item_frame, text="▼", width=25, height=20, fg_color="#34495E", hover_color="#2C3E50", state=down_state,
                                                 command=lambda idx=idx: self.move_queue_item_down(idx))
                        down_btn.pack(side="left", padx=2)

                        # 個別削除ボタン
                        del_btn = ctk.CTkButton(item_frame, text="Delete", width=50, height=20, fg_color="#C0392B", hover_color="#962D22",
                                                command=lambda idx=idx: self.delete_queue_item(idx))
                        del_btn.pack(side="right", padx=(5, 5))

        if self.streamer_core.is_running:
            self.after(500, self.update_ui_loop)

    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you want to quit the streamer?"):
            log_print("Shutting down streamer server and processes...")
            try:
                self.streamer_core.shutdown()
                self.api_server.stop()
            except Exception as e:
                log_print(f"Error during shutdown: {e}")
            self.destroy()
            os._exit(0)

def run_headless_mode(streamer_core, api_server):
    log_print("==================================================")
    log_print(f"VRCYouTube Headless API Server Mode Started")
    log_print(f"API Endpoints available on http://{streamer_core.config.get('host')}:{streamer_core.config.get('port')}/api/")
    log_print("Press Ctrl+C to terminate.")
    log_print("==================================================")

    def signal_handler(sig, frame):
        log_print("\n[Headless] Signal received. Shutting down...")
        streamer_core.shutdown()
        api_server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        while streamer_core.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        streamer_core.shutdown()
        api_server.stop()

def main():
    parser = argparse.ArgumentParser(description="VRCYouTube Streamer and API Server")
    parser.add_argument("--headless", "-hl", action="store_true", help="Run in headless API server mode without GUI")
    parser.add_argument("--tunnel", action="store_true", help="Explicitly enable Cloudflare tunnel")
    parser.add_argument("--no-tunnel", "-nt", action="store_true", help="Disable Cloudflare tunnel (run in local test mode)")
    parser.add_argument("--port", "-p", type=int, default=None, help="Port for API and HLS server (default: 8000 or config.json)")
    parser.add_argument("--host", type=str, default=None, help="Host address to bind (default: 127.0.0.1 or config.json)")

    args = parser.parse_args()

    # トンネル有効/無効の判定
    override_tunnel = None
    if args.tunnel:
        override_tunnel = True
    elif args.no_tunnel:
        override_tunnel = False

    # コアの初期化
    core = StreamerCore(
        override_port=args.port,
        override_host=args.host,
        override_enable_tunnel=override_tunnel
    )

    # cloudflared.exeの存在確認 (トンネル有効時のみ必須)
    if core.enable_tunnel and not os.path.exists(CLOUDFLARED_EXE):
        msg = f"cloudflared.exe is missing from the directory:\n{CLOUDFLARED_EXE}\n\nPlease place it in the same directory as this script, or launch with --no-tunnel for local testing."
        log_print(f"ERROR: {msg}")
        if not args.headless:
            try:
                ctk.set_appearance_mode("Dark")
                root = ctk.CTk()
                root.withdraw()
                messagebox.showerror("Error", msg)
            except Exception:
                pass
        sys.exit(1)

    # APIサーバーの初期化
    server = APIServer(streamer_core=core)
    if not server.start():
        log_print("Failed to start API/HLS server. Exiting.")
        sys.exit(1)

    # バックグラウンドタスク（トンネル・キュー監視）の開始
    core.start_background_tasks()

    if args.headless:
        run_headless_mode(core, server)
    else:
        app = App(core, server)
        app.mainloop()

if __name__ == "__main__":
    main()
