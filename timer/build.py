# -*- coding: utf-8 -*-
"""PyInstaller 打包脚本，由 build.bat 调用。

单独使用（已安装 PyInstaller 时）：
    python build.py
"""

import PyInstaller.__main__

PyInstaller.__main__.run([
    "--noconfirm",
    "--clean",
    "--onefile",
    "--noconsole",
    "--name", "倒计时提醒",
    "timer.py",
])
