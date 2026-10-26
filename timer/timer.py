#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""倒计时提醒 —— 一个始终置顶的 10 / 15 / 20 秒倒计时小工具。

倒计时结束时弹出提醒，提醒 3 秒后自动消失。
全局快捷键：小键盘连按 1 / 2 / 3 五次，分别启动 10 / 15 / 20 秒倒计时。
运行：python timer.py
"""

import ctypes
import math
import queue
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import font as tkfont

try:
    import winsound
except ImportError:  # 非 Windows 平台
    winsound = None

# ------------------------------------------------------------------ 主题色
BG = "#1c2028"
FG = "#eef1f7"
MUTED = "#8b93a6"
DIM = "#5b6376"
FAINT = "#454c5c"
DANGER = "#ff6b6b"
PANEL = "#272d3a"
PANEL_HOVER = "#343d4e"
TRACK = "#2e3543"
ACCENTS = {10: "#4f8cff", 15: "#2fc48d", 20: "#f5a623"}
HOVERS = {10: "#6a9fff", 15: "#47d7a0", 20: "#ffb84d"}
FONT = "Microsoft YaHei UI"
POPUP_MS = 3000

# ---------------------------------------------------------------- 全局快捷键
# 小键盘连按 1 / 2 / 3 五次，分别启动 10 / 15 / 20 秒倒计时
# VK_NUMPAD1 / VK_NUMPAD2 / VK_NUMPAD3；大键盘数字行不参与
TRIGGER_VKS = {0x61: 10, 0x62: 15, 0x63: 20}
# NumLock 关闭时，小键盘 1/2/3 会变成 End / Down / PageDown（无扩展键标志）。
# 映射为：虚拟键 -> (扫描码, 小键盘虚拟键)
NUMPAD_NUMLOCK_OFF = {
    0x23: (0x4F, 0x61),  # End      -> 小键盘 1
    0x28: (0x50, 0x62),  # Down     -> 小键盘 2
    0x22: (0x51, 0x63),  # PageDown -> 小键盘 3
}
LLKHF_EXTENDED = 0x01     # 方向键、编辑键区的 End/PageDown 会带这个标志
HOTKEY_PRESSES = 5
HOTKEY_GAP = 1.0          # 相邻两次按键的最大间隔（秒）
HOTKEYS_SUPPORTED = sys.platform == "win32"


def enable_dpi_awareness() -> None:
    """让窗口在高分屏上保持清晰。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ------------------------------------------------------- Windows 键盘钩子
WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
MODIFIER_VKS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift / Ctrl / Alt / Win

if HOTKEYS_SUPPORTED:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    _HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
    )

    _user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD
    ]
    _user32.SetWindowsHookExW.restype = ctypes.c_void_p
    _user32.CallNextHookEx.argtypes = [
        ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
    ]
    _user32.CallNextHookEx.restype = ctypes.c_ssize_t
    _user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    _user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND,
        wintypes.UINT, wintypes.UINT,
    ]
    _user32.GetMessageW.restype = ctypes.c_int
    _user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND,
        wintypes.UINT, wintypes.UINT, wintypes.UINT,
    ]
    _user32.PeekMessageW.restype = wintypes.BOOL
    _user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    _user32.DispatchMessageW.restype = ctypes.c_ssize_t
    _user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    _user32.PostThreadMessageW.restype = wintypes.BOOL
    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    _kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class HotkeyListener:
    """全局监听连按：连续按下同一个数字 5 次即触发对应时长。"""

    def __init__(self, triggers):
        self.triggers = triggers
        self.queue = queue.Queue()
        self._thread = None
        self._thread_id = 0
        self._hook = None
        self._hook_proc = None
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._down = set()
        self._seq_key = None
        self._seq_count = 0
        self._seq_last = 0.0

    def start(self):
        if not HOTKEYS_SUPPORTED:
            return
        self._thread = threading.Thread(target=self._run, name="hotkeys",
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stopping.set()
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if (self._thread is not None and self._thread.is_alive()
                and self._thread is not threading.current_thread()):
            self._thread.join(timeout=1.0)

    def _run(self):
        self._thread_id = _kernel32.GetCurrentThreadId()
        if self._stopping.is_set():
            return

        # 先创建线程消息队列，保证 PostThreadMessage 能找到它
        msg = wintypes.MSG()
        _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

        self._hook_proc = _HOOKPROC(self._on_key_event)
        self._hook = _user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc,
            _kernel32.GetModuleHandleW(None), 0,
        )
        self._ready.set()
        if not self._hook:
            return

        try:
            while True:
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _on_key_event(self, n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION:
                info = ctypes.cast(
                    l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)
                ).contents
                vk = self._normalize_vk(info.vkCode, info.scanCode, info.flags)
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    self._key_down(vk)
                elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                    self._down.discard(vk)
        except Exception:
            pass  # 钩子回调中绝不能抛出异常，否则会卡住键盘
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    @staticmethod
    def _normalize_vk(vk, scan_code, flags):
        """NumLock 关闭时把小键盘键还原成数字键（排除方向键/编辑键区）。"""
        if not flags & LLKHF_EXTENDED:
            mapped = NUMPAD_NUMLOCK_OFF.get(vk)
            if mapped and scan_code == mapped[0]:
                return mapped[1]
        return vk

    def _key_down(self, vk):
        if vk in self._down:
            return  # 按住不放产生的自动重复，不算一次按键
        self._down.add(vk)

        if vk not in self.triggers:
            self._reset_sequence()
            return

        # 带 Shift/Ctrl/Alt/Win 的组合键不算，避免输入符号时误触
        if any(_user32.GetAsyncKeyState(m) & 0x8000 for m in MODIFIER_VKS):
            self._reset_sequence()
            return

        now = time.monotonic()
        if vk == self._seq_key and now - self._seq_last <= HOTKEY_GAP:
            self._seq_count += 1
        else:
            self._seq_key = vk
            self._seq_count = 1
        self._seq_last = now

        if self._seq_count >= HOTKEY_PRESSES:
            seconds = self.triggers[vk]
            self._reset_sequence()
            self.queue.put_nowait(seconds)

    def _reset_sequence(self):
        self._seq_key = None
        self._seq_count = 0
        self._seq_last = 0.0


class CountdownApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)

        self.buttons = {}
        self.total = 0
        self.running = None          # 正在倒计时的秒数，None 表示空闲
        self.deadline = None         # time.monotonic() 截止时刻
        self.fraction = 0.0          # 进度条剩余比例
        self._hover = None
        self._timer_job = None
        self._reminder_job = None
        self._hotkey_job = None
        self._popup = None

        root.title("倒计时提醒")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_ui()
        root.update_idletasks()
        self._place_window()

        self._hotkeys = HotkeyListener(TRIGGER_VKS)
        self._hotkeys.start()
        self._hotkey_job = root.after(50, self._poll_hotkeys)

    # -------------------------------------------------------------- 界面
    def _px(self, value):
        return int(round(value * self.scale))

    def _build_ui(self) -> None:
        px = self._px
        self.f_num = tkfont.Font(family=FONT, size=44, weight="bold")
        self.f_word = tkfont.Font(family=FONT, size=22, weight="bold")
        self.f_unit = tkfont.Font(family=FONT, size=13)

        body = tk.Frame(self.root, bg=BG, padx=px(22), pady=px(16))
        body.pack()

        header = tk.Frame(body, bg=BG)
        header.pack(fill="x")
        tk.Label(header, text="倒计时", bg=BG, fg=FG,
                 font=(FONT, 11, "bold")).pack(side="left")
        tk.Label(header, text="始终置顶", bg=BG, fg=DIM,
                 font=(FONT, 9)).pack(side="right")

        # 大号剩余时间
        stage = tk.Frame(body, bg=BG,
                         height=self.f_num.metrics("linespace") + px(12))
        stage.pack(fill="x", pady=(px(2), px(2)))
        stage.pack_propagate(False)

        inner = tk.Frame(stage, bg=BG)
        inner.place(relx=0.5, rely=0.5, anchor="center")
        self.num = tk.Label(inner, text="就绪", bg=BG, fg=FG, font=self.f_word)
        self.num.pack(side="left")
        self.unit = tk.Label(inner, text="", bg=BG, fg=MUTED, font=self.f_unit)
        self.unit.pack(side="left", anchor="s", padx=(px(6), 0),
                       pady=(0, self.f_num.metrics("linespace") // 5))

        self.hint = tk.Label(body, text="选择下方时长开始", bg=BG, fg=MUTED,
                             font=(FONT, 9))
        self.hint.pack()

        # 进度条
        self.bar = tk.Canvas(body, height=px(10), bg=BG,
                             highlightthickness=0, bd=0)
        self.bar.pack(fill="x", pady=(px(14), px(15)))
        self.bar.bind("<Configure>", lambda _e: self._draw_bar())

        # 三个时长按钮
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        for col, secs in enumerate((10, 15, 20)):
            btn = tk.Button(
                row, text=f"{secs} 秒",
                command=lambda s=secs: self.start(s),
                bg=ACCENTS[secs], fg="#ffffff",
                activebackground=HOVERS[secs], activeforeground="#ffffff",
                relief="flat", bd=0, highlightthickness=0, takefocus=0,
                cursor="hand2", font=(FONT, 11, "bold"),
                width=6, pady=px(11),
            )
            btn.grid(row=0, column=col, sticky="ew",
                     padx=(0 if col == 0 else px(8), 0))
            row.columnconfigure(col, weight=1)
            btn.bind("<Enter>", lambda _e, s=secs: self._set_hover(s))
            btn.bind("<Leave>", lambda _e: self._set_hover(None))
            self.buttons[secs] = btn

        if HOTKEYS_SUPPORTED:
            for col, key in enumerate("123"):
                tk.Label(row, text=f"小键盘连按 {key} 五次", bg=BG, fg=DIM,
                         font=(FONT, 8)).grid(row=1, column=col,
                                              pady=(px(7), 0))

        self.stop_btn = tk.Button(
            body, text="停止", command=self.stop,
            bg=BG, fg=DIM, activebackground=BG, activeforeground=DANGER,
            disabledforeground=FAINT, relief="flat", bd=0,
            highlightthickness=0, takefocus=0, cursor="arrow",
            font=(FONT, 9), state="disabled",
        )
        self.stop_btn.pack(pady=(px(10), 0))

    def _place_window(self) -> None:
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        x = max(0, self.root.winfo_screenwidth() - w - self._px(24))
        y = self._px(48)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------ 倒计时
    def start(self, seconds: int) -> None:
        self._cancel_timer()
        self._cancel_reminder()
        self._close_popup()

        self.total = seconds
        self.running = seconds
        self.deadline = time.monotonic() + seconds

        self.num.configure(text=str(seconds), font=self.f_num, fg=FG)
        self.unit.configure(text="秒")
        self.hint.configure(text="倒计时中", fg=MUTED)
        self.stop_btn.configure(state="normal", cursor="hand2", fg=MUTED)
        self._refresh_buttons()
        self.fraction = 1.0
        self._draw_bar()
        self._tick()

    def _tick(self) -> None:
        if self.deadline is None:
            return
        left = self.deadline - time.monotonic()
        if left <= 0:
            self._finish()
            return
        self.num.configure(text=str(math.ceil(left)))
        self.fraction = left / self.total
        self._draw_bar()
        self._timer_job = self.root.after(100, self._tick)

    def _finish(self) -> None:
        self._timer_job = None
        seconds = self.total
        self.deadline = None
        self.running = None
        self.fraction = 0.0

        self.num.configure(text="时间到", font=self.f_word, fg=DANGER)
        self.unit.configure(text="")
        self.hint.configure(text=f"{seconds} 秒倒计时结束", fg=MUTED)
        self.stop_btn.configure(state="disabled", cursor="arrow", fg=DIM)
        self._refresh_buttons()
        self._draw_bar()

        self._play_alert()
        self._show_reminder(seconds)
        self._reminder_job = self.root.after(POPUP_MS, self._end_reminder)

    def stop(self) -> None:
        if self.running is None:
            return
        self._cancel_timer()
        self._cancel_reminder()
        self._close_popup()
        self._show_idle()

    def _show_idle(self) -> None:
        self.total = 0
        self.running = None
        self.deadline = None
        self.fraction = 0.0
        self.num.configure(text="就绪", font=self.f_word, fg=FG)
        self.unit.configure(text="")
        self.hint.configure(text="选择下方时长开始", fg=MUTED)
        self.stop_btn.configure(state="disabled", cursor="arrow", fg=DIM)
        self._refresh_buttons()
        self._draw_bar()

    # ------------------------------------------------------------ 提醒弹窗
    def _show_reminder(self, seconds: int) -> None:
        self._close_popup()
        px = self._px

        pop = tk.Toplevel(self.root)
        self._popup = pop
        pop.withdraw()
        pop.overrideredirect(True)
        pop.configure(bg=BG)

        card = tk.Frame(pop, bg=BG, padx=px(34), pady=px(22),
                        highlightbackground=DANGER,
                        highlightthickness=max(1, px(2)))
        card.pack()

        tk.Label(card, text="时间到！", bg=BG, fg=FG,
                 font=(FONT, 20, "bold")).pack()
        tk.Label(card, text=f"{seconds} 秒倒计时结束", bg=BG, fg=MUTED,
                 font=(FONT, 10)).pack(pady=(px(6), 0))
        tk.Label(card, text="提醒 3 秒后自动消失", bg=BG, fg=FAINT,
                 font=(FONT, 8)).pack(pady=(px(10), 0))

        for widget in (pop, card, *card.winfo_children()):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _e: self._end_reminder())

        pop.update_idletasks()
        w, h = pop.winfo_reqwidth(), pop.winfo_reqheight()
        x = (pop.winfo_screenwidth() - w) // 2
        y = (pop.winfo_screenheight() - h) // 3
        pop.geometry(f"{w}x{h}+{x}+{y}")
        pop.attributes("-topmost", True)
        pop.attributes("-alpha", 0.0)
        pop.deiconify()
        pop.lift()
        self._fade_in(pop, 0)

    def _fade_in(self, pop, step: int) -> None:
        if pop is not self._popup or not pop.winfo_exists():
            return
        alpha = min(1.0, (step + 1) / 6)
        try:
            pop.attributes("-alpha", alpha)
            if alpha < 1.0:
                pop.after(18, self._fade_in, pop, step + 1)
        except tk.TclError:
            pass

    def _end_reminder(self) -> None:
        self._cancel_reminder()
        self._close_popup()
        if self.deadline is None:
            self._show_idle()

    def _close_popup(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None

    # ------------------------------------------------------------ 小工具
    def _cancel_timer(self) -> None:
        if self._timer_job is not None:
            try:
                self.root.after_cancel(self._timer_job)
            except tk.TclError:
                pass
            self._timer_job = None

    def _cancel_reminder(self) -> None:
        if self._reminder_job is not None:
            try:
                self.root.after_cancel(self._reminder_job)
            except tk.TclError:
                pass
            self._reminder_job = None

    def _set_hover(self, secs) -> None:
        self._hover = secs
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        for secs, btn in self.buttons.items():
            hovered = self._hover == secs
            if self.running is None:
                bg = HOVERS[secs] if hovered else ACCENTS[secs]
                fg = "#ffffff"
            elif self.running == secs:
                bg = ACCENTS[secs]
                fg = "#ffffff"
            else:  # 倒计时进行中，其他时长按钮变暗，点击可切换
                bg = PANEL_HOVER if hovered else PANEL
                fg = FG if hovered else DIM
            btn.configure(bg=bg, fg=fg,
                          activebackground=HOVERS[secs],
                          activeforeground="#ffffff")

    def _draw_bar(self) -> None:
        self.bar.delete("all")
        width = self.bar.winfo_width()
        if width <= 1:
            return
        y = self.bar.winfo_height() // 2
        x0, x1 = self._px(4), width - self._px(4)
        if x1 <= x0:
            return
        self.bar.create_line(x0, y, x1, y, fill=TRACK,
                             width=self._px(5), capstyle="round")
        frac = max(0.0, min(1.0, self.fraction))
        if frac > 0:
            color = ACCENTS.get(self.running, MUTED)
            self.bar.create_line(x0, y, max(x0 + 1, x0 + (x1 - x0) * frac), y,
                                 fill=color, width=self._px(5),
                                 capstyle="round")

    def _play_alert(self) -> None:
        if winsound is None:
            try:
                self.root.bell()
            except tk.TclError:
                pass
            return
        try:
            winsound.PlaySound(
                "SystemExclamation",
                winsound.SND_ALIAS | winsound.SND_ASYNC,
            )
        except RuntimeError:
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

    def _poll_hotkeys(self) -> None:
        """在 Tk 主线程里取钩子线程收到的快捷键事件。"""
        self._hotkey_job = None
        try:
            while True:
                seconds = self._hotkeys.queue.get_nowait()
                self.root.deiconify()
                self.root.lift()
                self.start(seconds)
        except queue.Empty:
            pass
        self._hotkey_job = self.root.after(50, self._poll_hotkeys)

    def close(self) -> None:
        self._cancel_timer()
        self._cancel_reminder()
        self._close_popup()
        if self._hotkey_job is not None:
            try:
                self.root.after_cancel(self._hotkey_job)
            except tk.TclError:
                pass
            self._hotkey_job = None
        self._hotkeys.stop()
        self.root.destroy()


def main() -> None:
    enable_dpi_awareness()
    root = tk.Tk()
    CountdownApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
