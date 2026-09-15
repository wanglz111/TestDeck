#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""app.py — pywebview 原生窗外壳

在后台启动 serve.py，前台创建一个置顶的无边框原生窗。
"""
import threading
import time
import sys

try:
    import webview
except ImportError:
    print("⚠️  pywebview 未安装")
    print("请运行：pip install pywebview")
    sys.exit(1)

from serve import serve_in_thread

print("=" * 60)
print("测试执行器 — 原生窗模式")
print("=" * 60)
print()

# 后台启动 HTTP 服务
print("✓ 启动后端服务...")
threading.Thread(target=serve_in_thread, daemon=True).start()

# 等待服务器启动
time.sleep(1)

# 获取屏幕尺寸
try:
    screen = webview.screens[0]
    screen_width = screen.width
    screen_height = screen.height
except:
    screen_width = 1920
    screen_height = 1080

# 计算窗口位置：贴右侧
window_width = 420
window_height = 900
x = screen_width - window_width - 24
y = 24

print(f"✓ 创建原生窗（{window_width}x{window_height}，位置 {x},{y}）...")
print()

# 创建置顶窗口
window = webview.create_window(
    "测试执行器",
    "http://127.0.0.1:8765",
    width=window_width,
    height=window_height,
    x=x,
    y=y,
    on_top=True,
    frameless=True,
    easy_drag=True,
    resizable=True,
    min_size=(360, 600)
)

print("✓ 窗口已打开（常驻置顶）")
print()
print("按窗口右上角关闭按钮退出")
print()

webview.start()
