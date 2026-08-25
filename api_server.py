import os
import sys
import re
import json
import http.server
import socketserver
import threading
import time
import ipaddress
from urllib.parse import urlparse
from streamer_core import HLS_DIR, StreamerCore, log_print

def get_ui_html():
    """ui/index.html または plugin/ui/index.html が存在する場合は優先して読み込み、無ければ内蔵テンプレートを返す"""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html"),
        os.path.join(os.getcwd(), "ui", "index.html"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugin", "ui", "index.html"),
        os.path.join(os.getcwd(), "plugin", "ui", "index.html"),
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
    return HTML_PLAYER_TEMPLATE


HTML_PLAYER_TEMPLATE = """<!DOCTYPE html>
<html lang="ja" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VRCYouTube Streamer & Web Remote</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Remix Icon CDN -->
    <link href="https://cdn.jsdelivr.net/npm/remixicon@4.2.0/fonts/remixicon.css" rel="stylesheet">
    <!-- Hls.js for Live Stream Inline Preview -->
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        background: '#121214',
                        card: '#18181b',
                        'card-muted': '#202024',
                        border: '#27272a',
                        'border-hover': '#3f3f46',
                        muted: '#71717a',
                        'muted-foreground': '#a1a1aa',
                        primary: '#38bdf8',
                        'primary-hover': '#0284c7',
                        accent: '#f43f5e',
                        success: '#22c55e',
                        warning: '#f59e0b',
                        danger: '#ef4444',
                    },
                    fontFamily: {
                        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
                    }
                }
            }
        }
    </script>
    <style>
        /* Custom scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: #121214;
        }
        ::-webkit-scrollbar-thumb {
            background: #27272a;
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #3f3f46;
        }
        .drag-handle {
            cursor: grab;
        }
        .drag-handle:active {
            cursor: grabbing;
        }
        .dragging {
            opacity: 0.35;
            transform: scale(0.99);
        }
        .drag-over {
            border-top: 2px solid #38bdf8 !important;
        }
    </style>
</head>
        let currentLoopState = false;
        let currentShuffleState = false;
        let currentRadioState = false;
        let currentRadioBg = "card";
        let currentPhotoAdvance = false;
        let isCurrentItemImage = false;
        let userPermissions = {
            allow_web_queue_add: true,
            allow_web_queue_edit: true,
            allow_web_playback_control: true
        };

        // 1. URLクリックでコピー
        hlsUrlSpan.addEventListener('click', () => {
            const urlText = hlsUrlSpan.textContent.trim();
            if (urlText && !urlText.startsWith("(")) {
                navigator.clipboard.writeText(urlText).then(() => {
                    copyMsg.style.display = "block";
                    setTimeout(() => { copyMsg.style.display = "none"; }, 2500);
                });
            }
        });

        // 2. メッセージ通知
        function showMsg(text, isError) {
            msgBox.textContent = text;
            msgBox.className = "msg-box " + (isError ? "msg-error" : "msg-success");
            msgBox.style.display = "block";
            setTimeout(() => { msgBox.style.display = "none"; }, 5000);
        }

        function showPhotoMsg(text, isError) {
            photoMsgBox.textContent = text;
            photoMsgBox.className = "msg-box " + (isError ? "msg-error" : "msg-success");
            photoMsgBox.style.display = "block";
            setTimeout(() => { photoMsgBox.style.display = "none"; }, 5000);
        }

        // 3. 写真アップロード (Share Photo) & Drag and Drop (複数対応)
        if (uploadZone) {
            ['dragenter', 'dragover'].forEach(eventName => {
                uploadZone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    uploadZone.classList.add('dragover');
                }, false);
            });
            ['dragleave', 'drop'].forEach(eventName => {
                uploadZone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    uploadZone.classList.remove('dragover');
                }, false);
            });
            uploadZone.addEventListener('drop', (e) => {
                const dt = e.dataTransfer;
                const files = dt.files;
                if (files && files.length > 0) {
                    handlePhotoUpload(files);
                }
            });
        }

        async function handlePhotoUpload(files) {
            if (!files || files.length === 0) return;
            if (!userPermissions.allow_web_queue_add) {
                showPhotoMsg("⚠ ホストによって写真追加が無効化されています", true);
                return;
            }

            const fileList = Array.from(files);
            const total = fileList.length;
            let successCount = 0;
            let failCount = 0;

            for (let i = 0; i < total; i++) {
                const file = fileList[i];
                if (file.size > 20 * 1024 * 1024) {
                    showPhotoMsg(`⚠ ファイル「${file.name}」が大きすぎます (最大20MB)`, true);
                    failCount++;
                    continue;
                }

                if (total > 1) {
                    showPhotoMsg(`⏳ 写真をアップロード中... (${i + 1}/${total})`, false);
                } else {
                    showPhotoMsg("⏳ 写真をアップロード中...", false);
                }

                const formData = new FormData();
                formData.append('file', file);

                try {
                    const res = await fetch('/api/upload', {
                        method: 'POST',
                        body: formData
                    }).then(r => r.json());

                    if (res.success) {
                        successCount++;
                    } else {
                        failCount++;
                    }
                } catch (e) {
                    failCount++;
                }
            }

            document.getElementById('photo-input').value = "";
            fetchStatus();

            if (failCount === 0) {
                showPhotoMsg(`✓ ${successCount} 枚の写真をキューに追加しました！`, false);
            } else {
                showPhotoMsg(`✓ ${successCount} 枚追加完了 (${failCount} 枚失敗)`, true);
            }
        }

        // 4. 動画追加処理 (Add to Queue)
        function handleAddQueue() {
            if (!userPermissions.allow_web_queue_add) {
                showMsg("⚠ ホストによって動画追加が無効化されています", true);
                return;
            }
            const url = urlInput.value.trim();
            if (!url) return;

            addBtn.disabled = true;
            addBtn.textContent = "追加中...";

            fetch('/api/queue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    showMsg("✓ " + (res.message || "キューに追加しました！"), false);
                    urlInput.value = "";
                    fetchStatus();
                } else {
                    showMsg("⚠ " + (res.message || "追加に失敗しました"), true);
                }
            })
            .catch(e => {
                showMsg("⚠ 通信エラーが発生しました: " + e, true);
            })
            .finally(() => {
                addBtn.disabled = false;
                addBtn.textContent = "キューに追加";
            });
        }

        addBtn.addEventListener('click', handleAddQueue);
        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleAddQueue();
        });

        // 5. 再生コントロール操作
        function sendControl(action, payload = {}) {
            return fetch('/api/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: action, ...payload })
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    fetchStatus();
                    return res;
                } else {
                    showMsg("⚠ " + (res.message || "操作が拒否されました"), true);
                }
            })
            .catch(e => {
                showMsg("⚠ 通信エラー: " + e, true);
            });
        }

        function skipCurrentVideo() {
            if (!userPermissions.allow_web_playback_control) return;
            sendControl('skip').then(() => showMsg("✓ スキップをリクエストしました", false));
        }

        function togglePhotoAdvance() {
            if (!userPermissions.allow_web_playback_control) return;
            sendControl('set_image_auto_advance', { enabled: !currentPhotoAdvance });
        }

        function toggleRadio() {
            if (!userPermissions.allow_web_playback_control) return;
            sendControl('set_radio_mode', { enabled: !currentRadioState });
        }

        function changeRadioBg(val) {
            if (!userPermissions.allow_web_playback_control) return;
            sendControl('set_radio_bg_source', { source: val }).then(res => {
                if (res && res.success) {
                    showMsg("✓ ラジオ背景を切り替えました: " + val, false);
                }
            });
        }

        function changeDuration(val) {
            if (!userPermissions.allow_web_playback_control) return;
            sendControl('set_image_duration', { duration: parseInt(val, 10) });
        }

        function shuffleNow() {
            if (!userPermissions.allow_web_playback_control) return;
            sendControl('shuffle').then(() => showMsg("✓ キューをシャッフルしました", false));
        }

        function toggleLoop() {
            if (!userPermissions.allow_web_playback_control) return;
            sendControl('set_loop', { enabled: !currentLoopState });
        }

        function toggleShuffle() {
            if (!userPermissions.allow_web_playback_control) return;
            sendControl('set_shuffle', { enabled: !currentShuffleState });
        }

        function moveQueueItem(idx, direction) {
            if (!userPermissions.allow_web_queue_edit) return;
            const targetIdx = idx + direction;
            sendControl('move_item', { from_index: idx, to_index: targetIdx });
        }

        function deleteQueueItem(idx) {
            if (!userPermissions.allow_web_queue_edit) return;
            sendControl('delete_item', { index: idx }).then(res => {
                if (res && res.success) {
                    showMsg("✓ アイテムを削除しました", false);
                }
            });
        }

        // 6. 定期ステータス・キュー取得
        function formatDuration(sec) {
            if (!sec || sec <= 0) return "";
            const m = Math.floor(sec / 60);
            const s = sec % 60;
            return m + ":" + (s < 10 ? "0" : "") + s;
        }

        function fetchStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    // ストリームURL更新
                    if (data.stream_url) {
                        hlsUrlSpan.textContent = data.stream_url;
                    } else if (data.tunnel_url) {
                        hlsUrlSpan.textContent = data.tunnel_url + '/stream.m3u8';
                    }

                    // 権限設定の同期
                    if (data.permissions) {
                        userPermissions = data.permissions;
                        addBtn.disabled = !userPermissions.allow_web_queue_add;
                        btnSkip.disabled = !userPermissions.allow_web_playback_control;
                        btnPhotoPause.disabled = !userPermissions.allow_web_playback_control;
                        btnRadio.disabled = !userPermissions.allow_web_playback_control;
                        btnShuffleNow.disabled = !userPermissions.allow_web_playback_control;
                        btnLoop.disabled = !userPermissions.allow_web_playback_control;
                        btnShuffle.disabled = !userPermissions.allow_web_playback_control;
                        if (selectRadioBg) selectRadioBg.disabled = !userPermissions.allow_web_playback_control;
                        if (selectDuration) selectDuration.disabled = !userPermissions.allow_web_playback_control;
                    }

                    // 写真関連状態の同期
                    isCurrentItemImage = !!data.is_image;
                    currentPhotoAdvance = data.image_auto_advance !== undefined ? !!data.image_auto_advance : !data.image_paused;
                    btnPhotoPause.textContent = currentPhotoAdvance ? "⏱ 自動送り: ON" : "⏱ 自動送り: OFF";
                    btnPhotoPause.className = "btn-sm " + (currentPhotoAdvance ? "btn-active" : "");

                    if (data.image_display_duration && selectDuration && selectDuration.value != data.image_display_duration) {
                        selectDuration.value = String(data.image_display_duration);
                    }

                    // モード状態の同期
                    currentLoopState = !!data.loop_queue;
                    currentShuffleState = !!data.shuffle;
                    currentRadioState = !!data.radio_mode;
                    currentRadioBg = data.radio_bg_source || "card";

                    btnLoop.textContent = currentLoopState ? "🔁 ループ: ON" : "🔁 ループ: OFF";
                    btnLoop.className = "btn-sm " + (currentLoopState ? "btn-active" : "");

                    btnShuffle.textContent = currentShuffleState ? "🔀 シャッフル: ON" : "🔀 シャッフル: OFF";
                    btnShuffle.className = "btn-sm " + (currentShuffleState ? "btn-active" : "");

                    btnRadio.textContent = currentRadioState ? "📻 BGM/ラジオ: ON" : "📻 BGM/ラジオ: OFF";
                    btnRadio.className = "btn-sm " + (currentRadioState ? "btn-active" : "");

                    if (data.radio_bg_source && selectRadioBg && selectRadioBg.value != data.radio_bg_source) {
                        selectRadioBg.value = data.radio_bg_source;
                    }

                    // モードバッジ
                    let badges = [];
                    if (data.loop_queue) badges.push("🔁 Loop ON");
                    if (data.shuffle) badges.push("🔀 Shuffle ON");
                    if (data.radio_mode) badges.push("📻 Radio/BGM");
                    if (isCurrentItemImage) badges.push("🖼 Photo");
                    modeBadges.textContent = badges.join(" • ");

                    // キュー一覧描画
                    const items = data.queue || [];
                    const curr = data.current_video;
                    const totalCount = items.length + (curr ? 1 : 0);
                    queueHeaderTitle.textContent = "🎵 プレイリスト / キュー (" + totalCount + " items)";

                    let html = "";
                    if (curr) {
                        const currIcon = (curr.type === 'image' || (curr.title && curr.title.startsWith("🖼"))) ? "🖼" : "🎬";
                        html += '<li class="queue-item active">'
                              + '<span class="queue-idx">▶</span>'
                              + '<span style="margin-right:2px;">' + currIcon + '</span>'
                              + '<span class="queue-name" style="font-weight:600; color: #38bdf8;">' + escapeHtml(curr.title || "Unknown") + '</span>'
                              + '<span class="queue-duration">' + (curr.type === 'image' ? (curr.duration + 's') : formatDuration(curr.duration)) + '</span>'
                              + '</li>';
                    }
                    if (items.length === 0 && !curr) {
                        html = '<li style="color: var(--text-muted); font-size: 12px; padding: 8px;">(キューは空です。URLまたは写真を追加してください)</li>';
                    } else {
                        items.forEach((item, idx) => {
                            let actionBtns = "";
                            if (userPermissions.allow_web_queue_edit) {
                                const upDisabled = (idx === 0) ? 'disabled style="opacity:0.3"' : '';
                                const downDisabled = (idx === items.length - 1) ? 'disabled style="opacity:0.3"' : '';
                                actionBtns = '<div class="item-actions">'
                                           + `<button class="item-action-btn" title="上へ移動" onclick="moveQueueItem(${idx}, -1)" ${upDisabled}>▲</button>`
                                           + `<button class="item-action-btn" title="下へ移動" onclick="moveQueueItem(${idx}, 1)" ${downDisabled}>▼</button>`
                                           + `<button class="item-action-btn del" title="削除" onclick="deleteQueueItem(${idx})">✕</button>`
                                           + '</div>';
                            }

                            const itemIcon = (item.type === 'image' || (item.title && item.title.startsWith("🖼"))) ? "🖼" : "🎬";
                            const durStr = (item.type === 'image' || (item.title && item.title.startsWith("🖼"))) ? (item.duration + 's') : formatDuration(item.duration);

                            html += '<li class="queue-item">'
                                  + '<span class="queue-idx">#' + (idx + 1) + '</span>'
                                  + '<span style="margin-right:2px;">' + itemIcon + '</span>'
                                  + '<span class="queue-name">' + escapeHtml(item.title || "Unknown") + '</span>'
                                  + '<span class="queue-duration">' + durStr + '</span>'
                                  + actionBtns
                                  + '</li>';
                        });
                    }
                    queueList.innerHTML = html;
                })
                .catch(() => {});
        }

        function escapeHtml(str) {
            return str.replace(/[&<>'"]/g, 
                tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
            );
        }

        fetchStatus();
        setInterval(fetchStatus, 3500);

        // 5. HLS Web Player コントロール
        video.addEventListener('playing', () => {
            statusDiv.textContent = "配信中 / Stream Active (Playing)";
            statusDiv.style.backgroundColor = "#047857";
        });
        video.addEventListener('pause', () => {
            statusDiv.textContent = "一時停止中 / Paused";
            statusDiv.style.backgroundColor = "#475569";
        });
        video.addEventListener('waiting', () => {
            statusDiv.textContent = "バッファリング中 / Buffering...";
            statusDiv.style.backgroundColor = "#b45309";
        });
        statusDiv.addEventListener('click', () => {
            if (video.paused) {
                video.play().catch(e => console.log("Play failed:", e));
            }
        });

        function checkStream() {
            fetch(streamUrl, { method: 'HEAD' })
                .then(response => {
                    if (response.ok) {
                        statusDiv.textContent = "配信中 / Stream Active (Loading...)";
                        statusDiv.style.backgroundColor = "#065f46";
                        initPlayer();
                    } else {
                        statusDiv.textContent = "待機中 / Standby (キュー待機画面配信中)";
                        statusDiv.style.backgroundColor = "#1e293b";
                        initPlayer();
                    }
                })
                .catch(() => {
                    statusDiv.textContent = "接続待機中 / Waiting for server...";
                    statusDiv.style.backgroundColor = "#475569";
                    destroyPlayer();
                    setTimeout(checkStream, 3000);
                });
        }

        let hls = null;
        function initPlayer() {
            if (hls || video.src) return;
            if (Hls.isSupported()) {
                hls = new Hls({
                    maxBufferLength: 30,
                    liveSyncDurationCount: __LIVE_SYNC_DURATION_COUNT__,
                    manifestLoadingMaxRetry: 10,
                    manifestLoadingRetryDelay: 1000
                });
                hls.loadSource(streamUrl);
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, function() {
                    video.play().catch(e => {
                        statusDiv.textContent = "配信中 (クリックしてプレビュー再生)";
                    });
                });
                hls.on(Hls.Events.ERROR, function(event, data) {
                    if (data.fatal) {
                        destroyPlayer();
                        setTimeout(checkStream, 2000);
                    }
                });
            } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = streamUrl;
            }
        }

        function destroyPlayer() {
            if (hls) {
                hls.destroy();
                hls = null;
            }
            video.src = "";
            video.load();
        }

        checkStream();
    </script>
</body>
</html>
"""

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

RATE_LIMIT_LOCK = threading.Lock()
LAST_QUEUE_REQUESTS = {} # {ip: timestamp}
QUEUE_RATE_LIMIT_SECONDS = 2.5
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_UPLOAD_BODY_BYTES = 20 * 1024 * 1024 # 20MB

def parse_multipart_file(body_bytes, content_type_header):
    """multipart/form-data からファイルバイナリとファイル名を取得"""
    m = re.search(r'boundary=([^;]+)', content_type_header)
    if not m:
        return None, None
    boundary = m.group(1).strip().strip('"').encode("utf-8")
    parts = body_bytes.split(b"--" + boundary)
    for part in parts:
        if b"filename=" in part:
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                header_end = part.find(b"\n\n")
                if header_end == -1:
                    continue
                body_start = header_end + 2
            else:
                body_start = header_end + 4
            headers_part = part[:header_end].decode("utf-8", errors="ignore")
            m_fn = re.search(r'filename="([^"]+)"', headers_part)
            filename = m_fn.group(1) if m_fn else "photo.jpg"
            file_data = part[body_start:].rstrip(b"\r\n--")
            return file_data, filename
    return None, None

class APIAndHLSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, streamer_core=None, shutdown_callback=None, **kwargs):
        self.streamer_core = streamer_core
        self.shutdown_callback = shutdown_callback
        super().__init__(*args, directory=HLS_DIR, **kwargs)

    def _self_origins(self):
        """自分自身のオリジンとして認めるURLの集合"""
        port = self.streamer_core.config.get("port", 8000) if self.streamer_core else 8000
        origins = set()
        for host in ("127.0.0.1", "localhost", "[::1]"):
            origins.add(f"http://{host}:{port}")

        from streamer_core import get_local_ip
        local_ip = get_local_ip()
        origins.add(f"http://{local_ip}:{port}")

        raw_host = self.headers.get("Host", "")
        if raw_host:
            origins.add(f"http://{raw_host}")
            origins.add(f"https://{raw_host}")

        tunnel = (self.streamer_core.tunnel_raw_url if self.streamer_core else "") or ""
        if tunnel:
            origins.add(tunnel.rstrip("/"))
        return origins

    def _origin_is_self(self):
        """
        CSRF対策: Originヘッダが自分自身のオリジンか判定。
        ブラウザはPOSTに必ずOriginを付けるため、「Origin無し」= 非ブラウザ由来
        （VRCBeacon等のネイティブ/サーバサイドクライアント）とみなして許可する。
        """
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        return origin.rstrip("/") in self._self_origins()

    def _host_header_is_safe(self):
        """
        DNSリビンディング対策: Hostヘッダがドメイン名の場合は拒否する。
        攻撃者ドメインを 127.0.0.1 に解決させる手口はHostが独自ドメインになるため弾ける。
        """
        raw_host = self.headers.get("Host", "")
        if not raw_host:
            return True
        hostname = urlparse(f"http://{raw_host}").hostname or ""
        hostname = hostname.lower()
        if hostname in ("localhost", ""):
            return True
        try:
            ipaddress.ip_address(hostname)
            return True  # IPリテラル直打ちはリビンディングの対象外
        except ValueError:
            pass
        tunnel = (self.streamer_core.tunnel_raw_url if self.streamer_core else "") or ""
        tunnel_host = (urlparse(tunnel).hostname or "").lower() if tunnel else ""
        return bool(tunnel_host) and hostname == tunnel_host

    def is_local_request(self):
        """
        ホストPC本人またはローカルテスト時の同一LANからの操作か判定。
        """
        if "cf-connecting-ip" in self.headers or "x-forwarded-for" in self.headers:
            return False
        client_ip = self.client_address[0] if self.client_address else ""
        
        # ループバック判定
        is_loopback = client_ip in ("127.0.0.1", "::1", "localhost")
        
        # プライベートLAN判定 (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
        is_private_lan = False
        try:
            ip_obj = ipaddress.ip_address(client_ip)
            is_private_lan = ip_obj.is_private or ip_obj.is_loopback
        except Exception:
            pass

        # トンネル無効（ローカルテストモード）時は同一LANからの全操作を許可
        is_tunnel_disabled = bool(self.streamer_core and not self.streamer_core.enable_tunnel)

        if not is_loopback and not (is_tunnel_disabled and is_private_lan):
            return False

        if not self._origin_is_self():
            log_print(f"[APIServer] Rejected local privilege: cross-site Origin {self.headers.get('Origin')!r}")
            return False
        if not self._host_header_is_safe():
            log_print(f"[APIServer] Rejected local privilege: suspicious Host {self.headers.get('Host')!r}")
            return False
        return True

    def check_rate_limit(self):
        """
        連投（DoS・スパム）防止レートリミット。
        キーにはCloudflareが上書きする CF-Connecting-IP か接続元IPのみを使う。
        X-Forwarded-For はクライアントが自由に詐称できるためキーに含めない。
        """
        client_ip = self.headers.get("cf-connecting-ip") or self.client_address[0]
        now = time.time()
        with RATE_LIMIT_LOCK:
            last_time = LAST_QUEUE_REQUESTS.get(client_ip, 0)
            if now - last_time < QUEUE_RATE_LIMIT_SECONDS:
                return False
            LAST_QUEUE_REQUESTS[client_ip] = now
            if len(LAST_QUEUE_REQUESTS) > 1000:
                for k in list(LAST_QUEUE_REQUESTS.keys()):
                    if now - LAST_QUEUE_REQUESTS[k] > 3600:
                        del LAST_QUEUE_REQUESTS[k]
            return True

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

    def send_json_response(self, status_code, data):
        response_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        accept_header = self.headers.get("Accept", "")

        # 1. API: Status
        if path == "/api/status":
            if self.streamer_core:
                data = self.streamer_core.get_status_data()
            else:
                data = {"status": "offline", "error": "Core not initialized"}
            self.send_json_response(200, data)
            return

        # 2. API: Config (ローカルホストのみ許可)
        elif path == "/api/config":
            if not self.is_local_request():
                self.send_json_response(403, {"error": "Forbidden: Configuration access is restricted to localhost."})
                return
            if self.streamer_core:
                self.send_json_response(200, self.streamer_core.config)
            else:
                self.send_json_response(500, {"error": "Core not initialized"})
            return

        # 3. API: QR Code Image
        elif path == "/api/qrcode":
            url = ""
            if self.streamer_core and self.streamer_core.tunnel_raw_url:
                url = self.streamer_core.tunnel_raw_url
            elif self.streamer_core:
                port = self.streamer_core.config.get("port", 8000)
                url = f"http://localhost:{port}"
            else:
                url = "http://localhost:8000"

            try:
                import qrcode
                import io
                qr = qrcode.QRCode(version=1, box_size=6, border=2)
                qr.add_data(url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                png_data = buf.getvalue()

                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png_data)))
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(png_data)
                return
            except Exception as e:
                log_print(f"[APIServer] Error generating QR image: {e}")
                self.send_json_response(500, {"error": "Failed to generate QR code"})
                return

        # 4. HTML Player (Root or /stream.m3u8 requested by browser)
        elif path == "/" or (path == "/stream.m3u8" and "text/html" in accept_header):
            live_sync = self.streamer_core.config.get("live_sync_duration_count", 4) if self.streamer_core else 4
            tunnel_stream_url = ""
            if self.streamer_core:
                if self.streamer_core.tunnel_url:
                    tunnel_stream_url = self.streamer_core.tunnel_url
                elif not self.streamer_core.enable_tunnel:
                    port = self.streamer_core.config.get("port", 8000)
                    tunnel_stream_url = f"http://localhost:{port}/stream.m3u8"
                else:
                    tunnel_stream_url = "(トンネルURL準備中...)"
            else:
                tunnel_stream_url = "(サーバー初期化中)"

            html = get_ui_html()
            html = html.replace("__LIVE_SYNC_DURATION_COUNT__", str(live_sync))
            html = html.replace("__TUNNEL_STREAM_URL__", tunnel_stream_url)
            content = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
            return

        # 4. Static HLS files (SimpleHTTPRequestHandler fallback)
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. API: Photo Upload (写真・画像アップロード)
        if path == "/api/upload":
            if not self.is_local_request() and not self.streamer_core.config.get("allow_web_queue_add", True):
                self.send_json_response(403, {
                    "success": False,
                    "message": "Forbidden: Adding photos from Web is disabled by the host."
                })
                return

            if not self.is_local_request() and not self.check_rate_limit():
                self.send_json_response(429, {
                    "success": False,
                    "message": "Rate limit exceeded. Please wait a few seconds before uploading another photo."
                })
                return

            try:
                content_len = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                content_len = 0

            if content_len <= 0 or content_len > MAX_UPLOAD_BODY_BYTES:
                self.send_json_response(413, {
                    "success": False,
                    "message": f"Invalid upload size or payload exceeds limit (max {MAX_UPLOAD_BODY_BYTES // (1024*1024)}MB)"
                })
                return

            if not self.streamer_core:
                self.send_json_response(500, {"success": False, "message": "Streamer core not available"})
                return

            body_bytes = self.rfile.read(content_len)
            content_type = self.headers.get("Content-Type", "")

            img_bytes, filename = None, "photo.jpg"
            if "multipart/form-data" in content_type:
                img_bytes, filename = parse_multipart_file(body_bytes, content_type)
            else:
                img_bytes = body_bytes
                filename = "uploaded_image.png"

            if not img_bytes:
                self.send_json_response(400, {"success": False, "message": "Could not parse image data from upload request"})
                return

            item = self.streamer_core.add_image_bytes(img_bytes, original_filename=filename)
            if item:
                self.send_json_response(200, {
                    "success": True,
                    "message": f"Successfully uploaded photo: {item.get('title')}",
                    "item": item
                })
            else:
                self.send_json_response(400, {
                    "success": False,
                    "message": "Failed to process image (unsupported image format or queue full)"
                })
            return

        # ボディ取得（JSON用サイズ上限 64KB）
        try:
            content_len = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            content_len = 0
        if content_len > MAX_REQUEST_BODY_BYTES:
            self.send_json_response(413, {
                "success": False,
                "message": f"Request body too large (max {MAX_REQUEST_BODY_BYTES} bytes)"
            })
            return
        body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            body_json = json.loads(body.decode("utf-8")) if body else {}
        except Exception as e:
            log_print(f"[APIServer] Error parsing JSON body: {e}")
            body_json = {}

        log_print(f"[APIServer] POST {path} body: {body_json}")

        # 2. API: Queue (動画・画像URL追加)
        if path == "/api/queue":
            # 外部からの動画追加 許可チェック
            if not self.is_local_request() and not self.streamer_core.config.get("allow_web_queue_add", True):
                self.send_json_response(403, {
                    "success": False,
                    "message": "Forbidden: Adding items from Web is disabled by the host."
                })
                return

            # レートリミット判定 (外部からの連投・DoS防止)
            if not self.is_local_request() and not self.check_rate_limit():
                self.send_json_response(429, {
                    "success": False,
                    "message": "Rate limit exceeded. Please wait a few seconds before adding another item."
                })
                return

            url = body_json.get("url", "").strip()
            if not url:
                log_print("[APIServer] /api/queue missing url")
                self.send_json_response(400, {"success": False, "message": "Missing 'url' parameter in request body"})
                return

            if not self.streamer_core:
                self.send_json_response(500, {"success": False, "message": "Streamer core not available"})
                return

            items = self.streamer_core.add_to_queue(url)
            log_print(f"[APIServer] add_to_queue returned {len(items)} items")
            if items:
                self.send_json_response(200, {
                    "success": True,
                    "message": f"Successfully added {len(items)} item(s) to queue",
                    "video": items[0],
                    "items": items
                })
            else:
                self.send_json_response(400, {
                    "success": False,
                    "message": "Failed to resolve or add URL (check URL format, safety, or queue capacity)"
                })
            return

        # 3. API: Control (再生・キュー制御)
        elif path == "/api/control":
            action = body_json.get("action", "").strip().lower()
            if not self.streamer_core:
                self.send_json_response(500, {"success": False, "message": "Streamer core not available"})
                return

            is_local = self.is_local_request()

            # 破壊的・全消去操作は常にローカルホスト限定
            if action in ("clear_queue", "stop") and not is_local:
                self.send_json_response(403, {
                    "success": False,
                    "message": f"Forbidden: Action '{action}' is restricted to localhost."
                })
                return

            # キュー編集操作（削除・並び替え）の権限チェック
            if action in ("delete_item", "move_item") and not is_local:
                if not self.streamer_core.config.get("allow_web_queue_edit", True):
                    self.send_json_response(403, {
                        "success": False,
                        "message": "Forbidden: Queue editing from Web is disabled by the host."
                    })
                    return

            # 再生制御操作の権限チェック
            if action in ("skip", "prev", "set_loop", "set_shuffle", "shuffle", "toggle_image_pause", "set_image_pause", "set_image_duration", "set_image_auto_advance", "set_radio_mode", "set_radio_bg_source") and not is_local:
                if not self.streamer_core.config.get("allow_web_playback_control", True):
                    self.send_json_response(403, {
                        "success": False,
                        "message": "Forbidden: Playback control from Web is disabled by the host."
                    })
                    return

            if action == "skip":
                self.streamer_core.skip()
                self.send_json_response(200, {"success": True, "message": "Action 'skip' processed."})
            elif action == "prev":
                ok = self.streamer_core.play_prev()
                if ok:
                    self.send_json_response(200, {"success": True, "message": "Action 'prev' processed."})
                else:
                    self.send_json_response(400, {"success": False, "message": "No previous item in history."})
            elif action == "set_radio_mode":
                enabled = bool(body_json.get("enabled", True))
                res = self.streamer_core.set_radio_mode(enabled)
                self.send_json_response(200, {"success": True, "radio_mode": res, "message": f"Radio mode set to {res}."})
            elif action == "set_radio_bg_source":
                source = str(body_json.get("source", "card")).strip().lower()
                res = self.streamer_core.set_radio_bg_source(source)
                self.send_json_response(200, {"success": True, "radio_bg_source": res, "message": f"Radio background source set to {res}."})
            elif action == "toggle_image_pause":
                paused = self.streamer_core.toggle_image_pause()
                self.send_json_response(200, {"success": True, "image_paused": paused, "image_auto_advance": not paused, "message": f"Photo pause toggled to {paused}."})
            elif action == "set_image_pause":
                paused = bool(body_json.get("paused", True))
                self.streamer_core.set_image_pause(paused)
                self.send_json_response(200, {"success": True, "image_paused": paused, "image_auto_advance": not paused, "message": f"Photo pause set to {paused}."})
            elif action == "set_image_duration":
                duration = body_json.get("duration", 15)
                sec = self.streamer_core.set_image_duration(duration)
                self.send_json_response(200, {"success": True, "duration": sec, "message": f"Photo duration set to {sec}s."})
            elif action == "set_image_auto_advance":
                enabled = bool(body_json.get("enabled", True))
                self.streamer_core.set_image_auto_advance(enabled)
                self.send_json_response(200, {"success": True, "image_auto_advance": enabled, "image_paused": not enabled, "message": f"Photo auto advance set to {enabled}."})
            elif action == "clear_queue":
                self.streamer_core.clear_queue()
                self.send_json_response(200, {"success": True, "message": "Action 'clear_queue' processed."})
            elif action == "stop":
                self.streamer_core.clear_queue()
                self.streamer_core.skip()
                self.send_json_response(200, {"success": True, "message": "Action 'stop' processed (queue cleared and stream skipped)."})
            elif action == "delete_item":
                idx = body_json.get("index")
                if idx is not None and isinstance(idx, int):
                    deleted = self.streamer_core.delete_queue_item(idx)
                    if deleted:
                        self.send_json_response(200, {"success": True, "message": f"Item at index {idx} removed", "item": deleted})
                    else:
                        self.send_json_response(400, {"success": False, "message": f"Index {idx} out of range"})
                else:
                    self.send_json_response(400, {"success": False, "message": "Missing or invalid 'index' parameter"})
            elif action == "move_item":
                from_idx = body_json.get("from_index")
                to_idx = body_json.get("to_index")
                if from_idx is not None and to_idx is not None:
                    ok = self.streamer_core.move_queue_item(int(from_idx), int(to_idx))
                    if ok:
                        self.send_json_response(200, {"success": True, "message": "Item moved successfully."})
                    else:
                        self.send_json_response(400, {"success": False, "message": "Invalid index range."})
                else:
                    self.send_json_response(400, {"success": False, "message": "Missing 'from_index' or 'to_index'"})
            elif action == "shuffle":
                self.streamer_core.shuffle_queue()
                self.send_json_response(200, {"success": True, "message": "Queue shuffled successfully."})
            elif action == "set_loop":
                enabled = body_json.get("enabled", True)
                res = self.streamer_core.set_loop(enabled)
                self.send_json_response(200, {"success": True, "loop_queue": res, "message": f"Loop queue set to {res}."})
            elif action == "set_shuffle":
                enabled = body_json.get("enabled", True)
                res = self.streamer_core.set_shuffle(enabled)
                self.send_json_response(200, {"success": True, "shuffle": res, "message": f"Shuffle set to {res}."})
            else:
                self.send_json_response(400, {
                    "success": False,
                    "message": f"Unknown action: '{action}'."
                })
            return

        # 3. API: Config (ローカルホスト限定)
        elif path == "/api/config":
            if not self.is_local_request():
                self.send_json_response(403, {"success": False, "message": "Forbidden: Configuration changes are restricted to localhost."})
                return
            if not self.streamer_core:
                self.send_json_response(500, {"success": False, "message": "Streamer core not available"})
                return
            saved = self.streamer_core.save_config(body_json)
            if saved:
                self.send_json_response(200, {"success": True, "config": self.streamer_core.config})
            else:
                self.send_json_response(500, {"success": False, "message": "Failed to save configuration"})
            return

        # 4. API: Shutdown (ローカルホスト限定)
        elif path == "/api/shutdown":
            if not self.is_local_request():
                self.send_json_response(403, {"success": False, "message": "Forbidden: Shutdown command is restricted to localhost."})
                return
            self.send_json_response(200, {"success": True, "message": "Server is shutting down..."})
            if self.shutdown_callback:
                threading.Thread(target=self.shutdown_callback, daemon=True).start()
            return

        else:
            self.send_json_response(404, {"error": "Not Found", "path": path})

    def end_headers(self):
        self.send_cors_headers()
        super().end_headers()

    def log_message(self, format, *args):
        # ログの抑制 (必要に応じてデバッグログ化)
        pass

class APIServer:
    def __init__(self, streamer_core, on_shutdown=None):
        self.streamer_core = streamer_core
        self.on_shutdown = on_shutdown
        self.httpd = None
        self.server_thread = None

    def create_handler(self, *args, **kwargs):
        return APIAndHLSHandler(*args, streamer_core=self.streamer_core,
                                shutdown_callback=self._trigger_shutdown, **kwargs)

    def _trigger_shutdown(self):
        time.sleep(0.5)
        if self.on_shutdown:
            self.on_shutdown()
        else:
            self.stop()
            if self.streamer_core:
                self.streamer_core.shutdown()
            sys.exit(0)

    def start(self):
        port = self.streamer_core.config.get("port", 8000)
        host = self.streamer_core.config.get("host", "0.0.0.0")
        
        # 0.0.0.0 または トンネル無効時（ローカルテスト時）は全インターフェースへバインドしてLAN内からアクセス可能にする
        is_tunnel_disabled = bool(self.streamer_core and not self.streamer_core.enable_tunnel)
        if host in ("0.0.0.0", "") or is_tunnel_disabled:
            bind_host = ""
        else:
            bind_host = host

        from streamer_core import get_local_ip
        local_ip = get_local_ip()

        try:
            self.httpd = ThreadedHTTPServer((bind_host, port), self.create_handler)
            log_print(f"[APIServer] Listening on {host or '0.0.0.0'}:{port} (Local: http://127.0.0.1:{port}, LAN: http://{local_ip}:{port})")
            self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.server_thread.start()
            return True
        except Exception as e:
            log_print(f"[APIServer] Failed to bind on {host}:{port}: {e}")
            return False

    def stop(self):
        if self.httpd:
            log_print("[APIServer] Stopping HTTP server...")
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None
