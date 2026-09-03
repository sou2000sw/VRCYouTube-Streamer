# -*- coding: utf-8 -*-
"""設定ウィンドウ（折りたたみ式アコーディオン）の単体テスト。

実際に Tk ウィンドウを生成して検証する。GUI のレイアウト変更では
「ウィジェットを作ったが pack() し忘れて画面から消える」「属性名が変わって
save_settings() が読めなくなる」といった、静かに壊れる事故が起きやすいため、
ソースの文字列検査ではなく実物を組み立てて確かめる。

画面のない環境では自動的にスキップする。
"""

import io
import json
import os
import re
import shutil

import pytest

import streamer_core

CONFIG_FILE = streamer_core.CONFIG_FILE
BACKUP_FILE = CONFIG_FILE + ".test_gui_settings.bak"


def _import_gui_streamer():
    """gui_streamer は import 時に sys.stdout/stderr を包み直すため、
    pytest のキャプチャを壊さないよう detach して元へ戻す。"""
    import sys
    saved_out, saved_err = sys.stdout, sys.stderr
    try:
        import gui_streamer
        return gui_streamer
    finally:
        for stream in (sys.stdout, sys.stderr):
            if stream is not saved_out and stream is not saved_err:
                try:
                    stream.detach()
                except Exception:
                    pass
        sys.stdout, sys.stderr = saved_out, saved_err


@pytest.fixture(scope="module")
def settings_window():
    """設定ウィンドウを1枚組み立てて渡す。config.json は必ず復元する。

    scope="module" にしてあるのは、同一プロセスで CTk のルートを何度も作り直すと
    まれに生成に失敗するため（実測: 3回に1回ほど skip に落ちた）。
    各テストは開いたセクションを閉じて返すので、1枚を共有して問題ない。
    """
    if os.path.exists(CONFIG_FILE):
        shutil.copy2(CONFIG_FILE, BACKUP_FILE)

    gui_streamer = _import_gui_streamer()
    import customtkinter as ctk

    core = streamer_core.StreamerCore(override_port=8999, override_enable_tunnel=False)
    try:
        root = ctk.CTk()
    except Exception as e:                      # 画面のない環境
        pytest.skip(f"GUIを開けない環境のためスキップ: {e}")
    root.withdraw()

    win = gui_streamer.SettingsWindow(root, core)
    root.update()
    try:
        yield win, root
    finally:
        try:
            win.destroy()
            root.destroy()
        except Exception:
            pass
        core.is_running = False
        if os.path.exists(BACKUP_FILE):
            shutil.copy2(BACKUP_FILE, CONFIG_FILE)
            os.remove(BACKUP_FILE)


def test_save_settings_reads_only_existing_widgets(settings_window):
    """save_settings() が読む self.* 属性が、実際に生成されていること。

    レイアウトを組み替えるときに属性を消す/改名すると、保存時に初めて落ちる。
    """
    print("\n--- 1. save_settings が読む属性の実在確認 ---")
    win, _root = settings_window
    src = io.open("gui_streamer.py", encoding="utf-8").read()
    start = src.index("    def save_settings(self):")
    end = src.index("\n    def ", start + 10)
    read_attrs = sorted(set(re.findall(r"self\.(\w+)\.(?:get|cget)\(", src[start:end])))

    assert read_attrs, "抽出に失敗（save_settings の書き方が変わった？）"
    missing = [a for a in read_attrs if not hasattr(win, a)]
    assert not missing, f"save_settings が読む属性が存在しない: {missing}"
    print(f"PASS: {len(read_attrs)} 個の属性すべて実在。")


def test_sections_are_collapsed_by_default_and_toggle(settings_window):
    """全セクションが既定で閉じており、見出しクリックで開閉すること。"""
    print("\n--- 2. セクションの既定状態と開閉 ---")
    win, root = settings_window
    sections = getattr(win, "_sections", [])
    assert len(sections) >= 8, f"セクション数が足りない: {len(sections)}"

    opened = [title for title, _btn, body, state in sections
              if state["open"] or body.winfo_ismapped()]
    assert not opened, f"既定では全セクションが閉じていること（開いていた: {opened}）"

    title, btn, body, _state = sections[0]
    btn.invoke()
    root.update()
    assert body.winfo_ismapped(), f"'{title}' を開いたのに表示されない"
    assert btn.cget("text").startswith("▼")

    btn.invoke()
    root.update()
    assert not body.winfo_ismapped(), f"'{title}' を閉じたのに表示されたまま"
    assert btn.cget("text").startswith("▶")
    print(f"PASS: {len(sections)} セクションすべて既定で閉じ、開閉も動作。")


def test_section_opens_directly_under_its_own_header(settings_window):
    """開いた中身が「その見出しの直下」に出ること。

    pack は呼んだ順に積まれるため、after= を付けないと中身がウィンドウ最下部
    （他のセクション見出しより後ろ）に現れる。どの見出しを押しても一番下に開く、
    という分かりにくい挙動になっていた。
    """
    print("\n--- 4. 見出しの直下に開く ---")
    win, root = settings_window
    sections = win._sections

    for index in (0, len(sections) // 2, len(sections) - 1):
        title, btn, body, _state = sections[index]
        btn.invoke()
        root.update()

        slaves = list(win.scroll_container.pack_slaves())
        assert body in slaves, f"'{title}' の中身が配置されていない"
        assert slaves.index(body) == slaves.index(btn) + 1, (
            f"'{title}' の中身が見出しの直下にない "
            f"(見出し={slaves.index(btn)} / 中身={slaves.index(body)} / 全{len(slaves)}要素)"
        )

        btn.invoke()
        root.update()
    print("PASS: どのセクションも自分の見出しの直下に開く。")


def test_saving_while_collapsed_keeps_settings(settings_window):
    """閉じたまま保存しても設定が失われないこと。

    折りたたみを destroy() で実装すると、閉じたセクションの値が既定値へ戻る
    （＝黙って設定が消える）。pack_forget であることをここで担保する。
    """
    print("\n--- 3. 閉じたまま保存しても設定が消えない ---")
    win, root = settings_window
    before = json.load(io.open(CONFIG_FILE, encoding="utf-8"))

    # save_settings() は完了時にモーダルダイアログを出し、最後にウィンドウを閉じる。
    # 差し替えないと、誰もクリックしないダイアログの前でテストが固まる
    # （実測: 利用者の画面にダイアログが出て、テストがその操作待ちになった）。
    gui_streamer = _import_gui_streamer()
    original_messagebox = gui_streamer.messagebox

    class _SilentMessagebox:
        shown = []

        @classmethod
        def showinfo(cls, title, message, **kw):
            cls.shown.append(("info", title, message))

        @classmethod
        def showerror(cls, title, message, **kw):
            cls.shown.append(("error", title, message))

        @classmethod
        def showwarning(cls, title, message, **kw):
            cls.shown.append(("warning", title, message))

    gui_streamer.messagebox = _SilentMessagebox
    try:
        win.save_settings()
        root.update()
    finally:
        gui_streamer.messagebox = original_messagebox

    errors = [m for m in _SilentMessagebox.shown if m[0] == "error"]
    assert not errors, f"保存時にエラーダイアログが出た: {errors}"

    after = json.load(io.open(CONFIG_FILE, encoding="utf-8"))
    # port はテスト用に上書き起動している値が保存されるため比較から除く
    diff = {k: (before.get(k), after.get(k))
            for k in set(before) | set(after)
            if k != "port" and before.get(k) != after.get(k)}
    assert not diff, f"閉じたまま保存しただけで設定が変化した: {diff}"
    print("PASS: 折りたたみ中の項目も保存で失われない。")
