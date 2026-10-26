#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""倒计时提醒 —— 一个始终置顶的 10 / 15 / 20 秒倒计时小工具。

倒计时结束时弹出提醒，提醒 3 秒后自动消失。
运行：python timer.py
"""

import ctypes
import math
import sys
import time
import tkinter as tk
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
        self._popup = None

        root.title("倒计时提醒")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_ui()
        root.update_idletasks()
        self._place_window()

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

    def close(self) -> None:
        self._cancel_timer()
        self._cancel_reminder()
        self._close_popup()
        self.root.destroy()


def main() -> None:
    enable_dpi_awareness()
    root = tk.Tk()
    CountdownApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
