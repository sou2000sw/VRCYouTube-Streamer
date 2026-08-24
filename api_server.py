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

HTML_PLAYER_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>VRCYouTube Stream & Request Web</title>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --border-color: #334155;
            --primary: #38bdf8;
            --primary-hover: #0284c7;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; }
        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 16px;
        }
        .container {
            max-width: 840px;
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 18px;
        }
        header {
            text-align: center;
            padding-bottom: 4px;
        }
        h1 {
            color: var(--primary);
            margin: 0 0 4px 0;
            font-size: 22px;
            font-weight: 700;
        }
        .subtitle {
            color: var(--text-muted);
            font-size: 13px;
            margin: 0;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }
        .video-wrapper {
            position: relative;
            padding-bottom: 56.25%; /* 16:9 */
            height: 0;
            background-color: #000;
            border-radius: 8px;
            overflow: hidden;
        }
        video {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
        }
        .status-badge {
            margin-top: 12px;
            padding: 10px;
            border-radius: 8px;
            background-color: #334155;
            font-size: 13px;
            font-weight: 600;
            text-align: center;
            transition: background-color 0.3s;
            cursor: pointer;
        }
        /* Forms */
        .form-row {
            display: flex;
            gap: 8px;
            margin-top: 8px;
        }
        input[type="text"] {
            flex: 1;
            background-color: #0f172a;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 14px;
            color: var(--text-main);
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }
        input[type="text"]:focus {
            border-color: var(--primary);
        }
        button {
            background-color: var(--primary);
            color: #0f172a;
            border: none;
            border-radius: 8px;
            padding: 12px 20px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: opacity 0.2s, background-color 0.2s;
            white-space: nowrap;
        }
        button:hover { background-color: var(--primary-hover); }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .msg-box {
            font-size: 12px;
            margin-top: 8px;
            padding: 8px 12px;
            border-radius: 6px;
            display: none;
        }
        .msg-success { background-color: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }
        .msg-error { background-color: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }
        /* URL & QR Card */
        .share-container {
            display: flex;
            gap: 16px;
            align-items: center;
            flex-wrap: wrap;
        }
        .qr-wrapper {
            background-color: #ffffff;
            padding: 10px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        .share-info {
            flex: 1;
            min-width: 240px;
        }
        .share-info code {
            display: block;
            background-color: #0f172a;
            color: var(--primary);
            padding: 10px 12px;
            border-radius: 6px;
            margin-top: 6px;
            word-break: break-all;
            user-select: all;
            font-family: monospace;
            font-size: 12px;
            border: 1px solid var(--border-color);
            cursor: pointer;
        }
        /* Queue List */
        .queue-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            flex-wrap: wrap;
            gap: 6px;
        }
        .queue-title {
            font-weight: 700;
            font-size: 15px;
            color: var(--text-main);
        }
        .control-btn-group {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }
        .btn-sm {
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 6px;
            background-color: #334155;
            color: var(--text-main);
        }
        .btn-sm:hover {
            background-color: #475569;
        }
        .btn-active {
            background-color: var(--primary) !important;
            color: #0f172a !important;
        }
        .btn-danger {
            background-color: rgba(239, 68, 68, 0.2);
            color: #f87171;
            border: 1px solid #dc2626;
        }
        .btn-danger:hover {
            background-color: #dc2626;
            color: #fff;
        }
        /* Photo Upload Dropzone */
        .upload-drop-zone {
            border: 2px dashed var(--border-color);
            border-radius: 8px;
            padding: 20px 14px;
            text-align: center;
            background-color: #0f172a;
            cursor: pointer;
            transition: border-color 0.2s, background-color 0.2s;
            margin-top: 8px;
        }
        .upload-drop-zone:hover, .upload-drop-zone.dragover {
            border-color: var(--primary);
            background-color: rgba(56, 189, 248, 0.05);
        }
        .select-sm {
            background-color: #0f172a;
            border: 1px solid var(--border-color);
            color: var(--text-main);
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 12px;
            outline: none;
            cursor: pointer;
        }
        .select-sm:focus {
            border-color: var(--primary);
        }
        .queue-list {
            list-style: none;
            padding: 0;
            margin: 0;
            display: flex;
            flex-direction: column;
            gap: 6px;
            max-height: 280px;
            overflow-y: auto;
        }
        .queue-item {
            background-color: #0f172a;
            border: 1px solid var(--border-color);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .queue-item.active {
            border-color: var(--primary);
            background-color: rgba(56, 189, 248, 0.08);
        }
        .queue-idx {
            color: var(--primary);
            font-weight: 700;
            font-size: 12px;
            min-width: 24px;
        }
        .queue-name {
            flex: 1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .queue-duration {
            color: var(--text-muted);
            font-size: 11px;
            margin-right: 4px;
        }
        .item-actions {
            display: flex;
            gap: 4px;
        }
        .item-action-btn {
            background-color: #1e293b;
            color: var(--text-main);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            cursor: pointer;
            line-height: 1.2;
        }
        .item-action-btn:hover {
            background-color: var(--primary);
            color: #0f172a;
        }
        .item-action-btn.del:hover {
            background-color: var(--danger);
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>VRCYouTube Web Request & Remote</h1>
            <p class="subtitle">Scan QR or enter YouTube URL / Photo to add videos & control the stream</p>
        </header>

        <!-- 1. Video Player Card -->
        <div class="card">
            <div class="video-wrapper">
                <video id="video" controls autoplay playsinline></video>
            </div>
            <div id="status" class="status-badge">Checking stream status...</div>
        </div>

        <!-- 2. Add Video Form Card -->
        <div class="card">
            <div class="queue-title">🎬 動画をリクエスト (Add Video)</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
                YouTubeの動画またはプレイリストURLを入力してキューに追加できます
            </div>
            <div class="form-row">
                <input type="text" id="url-input" placeholder="https://www.youtube.com/watch?v=... / プレイリストURL / 画像URL">
                <button id="add-btn">キューに追加</button>
            </div>
            <div id="msg-box" class="msg-box"></div>
        </div>

        <!-- 3. Share Photo Upload Card -->
        <div class="card">
            <div class="queue-title">🖼️ 写真・画像を共有 (Share Photo)</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
                スマートフォンやPCから写真をアップロードして配信スクリーンに表示できます
            </div>
            <div class="upload-drop-zone" id="upload-zone" onclick="document.getElementById('photo-input').click()">
                <input type="file" id="photo-input" accept="image/*" multiple style="display:none" onchange="handlePhotoUpload(this.files)">
                <div style="font-size: 26px; margin-bottom: 2px;">📷</div>
                <div style="font-size: 13px; font-weight: 600; color: var(--primary);">タップして写真を選択（複数選択可） / ドロップ</div>
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">JPEG, PNG, WebP, GIF (最大20MB/枚)</div>
            </div>
            <div id="photo-msg-box" class="msg-box"></div>
        </div>

        <!-- 4. Playback Controls Card -->
        <div class="card" id="playback-control-card">
            <div class="queue-header">
                <div class="queue-title">🎛️ 再生コントロール (Playback Control)</div>
                <div class="control-btn-group">
                    <button class="btn-sm" id="btn-skip" onclick="skipCurrentVideo()">⏭ スキップ (Skip)</button>
                    <button class="btn-sm" id="btn-photo-pause" onclick="togglePhotoAdvance()">⏱ 自動送り: OFF</button>
                    <button class="btn-sm" id="btn-radio-toggle" onclick="toggleRadio()">📻 BGM/ラジオ: OFF</button>
                    <button class="btn-sm" id="btn-shuffle-now" onclick="shuffleNow()">🔀 並び替え (Shuffle)</button>
                    <button class="btn-sm" id="btn-loop-toggle" onclick="toggleLoop()">🔁 ループ: OFF</button>
                    <button class="btn-sm" id="btn-shuffle-toggle" onclick="toggleShuffle()">🔀 シャッフル: OFF</button>
                </div>
            </div>
            <div style="margin-top: 8px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 12px; color: var(--text-muted); border-top: 1px solid var(--border-color); padding-top: 8px;">
                <span>⏱ 写真表示時間 (Photo Duration):</span>
                <select id="select-duration" class="select-sm" onchange="changeDuration(this.value)">
                    <option value="5">5 秒 (5s)</option>
                    <option value="10">10 秒 (10s)</option>
                    <option value="15" selected>15 秒 (15s)</option>
                    <option value="20">20 秒 (20s)</option>
                    <option value="30">30 秒 (30s)</option>
                    <option value="60">60 秒 (60s)</option>
                    <option value="120">120 秒 (120s)</option>
                </select>
            </div>
        </div>

        <!-- 4. VRChat URL & Mobile Share QR Card -->
        <div class="card">
            <div class="share-container">
                <div class="qr-wrapper">
                    <img id="qr-img" src="/api/qrcode" alt="Request QR Code" width="115" height="115" style="display:block; border-radius:4px; background:#fff;">
                </div>
                <div class="share-info">
                    <div style="font-size: 13px; font-weight: 600; color: #38bdf8;">
                        📱 スマホ共有用QRコード & VRChatストリームURL
                    </div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
                        QRコードをスマホで読み取ると、フレンドもこのリクエスト画面を開いて動画を追加・操作できます。<br>
                        VRChatプレイヤーに入力するURL（クリックしてコピー）:
                    </div>
                    <code id="hls-url" title="クリックしてコピー">__TUNNEL_STREAM_URL__</code>
                    <div id="copy-msg" style="font-size: 11px; color: var(--success); margin-top: 4px; display: none;">✓ URLをクリップボードにコピーしました！</div>
                </div>
            </div>
        </div>

        <!-- 5. Play Queue Card -->
        <div class="card">
            <div class="queue-header">
                <div class="queue-title" id="queue-header-title">🎵 プレイリスト / キュー (0 items)</div>
                <div id="mode-badges" style="font-size: 11px; color: var(--text-muted);"></div>
            </div>
            <ul class="queue-list" id="queue-list">
                <li style="color: var(--text-muted); font-size: 12px; padding: 8px;">(キューは空です)</li>
            </ul>
        </div>
    </div>

    <script>
        const video = document.getElementById('video');
        const statusDiv = document.getElementById('status');
        const hlsUrlSpan = document.getElementById('hls-url');
        const copyMsg = document.getElementById('copy-msg');
        const urlInput = document.getElementById('url-input');
        const addBtn = document.getElementById('add-btn');
        const msgBox = document.getElementById('msg-box');
        const photoMsgBox = document.getElementById('photo-msg-box');
        const uploadZone = document.getElementById('upload-zone');
        const queueList = document.getElementById('queue-list');
        const queueHeaderTitle = document.getElementById('queue-header-title');
        const modeBadges = document.getElementById('mode-badges');
        const btnSkip = document.getElementById('btn-skip');
        const btnPhotoPause = document.getElementById('btn-photo-pause');
        const btnRadio = document.getElementById('btn-radio-toggle');
        const btnShuffleNow = document.getElementById('btn-shuffle-now');
        const btnLoop = document.getElementById('btn-loop-toggle');
        const btnShuffle = document.getElementById('btn-shuffle-toggle');
        const selectDuration = document.getElementById('select-duration');
        const streamUrl = window.location.origin + '/stream.m3u8';

        let currentLoopState = false;
        let currentShuffleState = false;
        let currentRadioState = false;
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
                        selectDuration.disabled = !userPermissions.allow_web_playback_control;
                    }

                    // 写真関連状態の同期
                    isCurrentItemImage = !!data.is_image;
                    currentPhotoAdvance = data.image_auto_advance !== undefined ? !!data.image_auto_advance : !data.image_paused;
                    btnPhotoPause.textContent = currentPhotoAdvance ? "⏱ 自動送り: ON" : "⏱ 自動送り: OFF";
                    btnPhotoPause.className = "btn-sm " + (currentPhotoAdvance ? "btn-active" : "");

                    if (data.image_display_duration && selectDuration.value != data.image_display_duration) {
                        selectDuration.value = String(data.image_display_duration);
                    }

                    // モード状態の同期
                    currentLoopState = !!data.loop_queue;
                    currentShuffleState = !!data.shuffle;
                    currentRadioState = !!data.radio_mode;

                    btnLoop.textContent = currentLoopState ? "🔁 ループ: ON" : "🔁 ループ: OFF";
                    btnLoop.className = "btn-sm " + (currentLoopState ? "btn-active" : "");

                    btnShuffle.textContent = currentShuffleState ? "🔀 シャッフル: ON" : "🔀 シャッフル: OFF";
                    btnShuffle.className = "btn-sm " + (currentShuffleState ? "btn-active" : "");

                    btnRadio.textContent = currentRadioState ? "📻 BGM/ラジオ: ON" : "📻 BGM/ラジオ: OFF";
                    btnRadio.className = "btn-sm " + (currentRadioState ? "btn-active" : "");

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

            html = HTML_PLAYER_TEMPLATE.replace("__LIVE_SYNC_DURATION_COUNT__", str(live_sync))
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
