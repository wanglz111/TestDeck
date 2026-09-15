#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""envutil.py — 极小的 .env 加载器（不引第三方依赖）

为什么不用 python-dotenv：只为了读一个 key=value 列表，不值得加一个包。
行为约定：**已存在的环境变量优先**（setdefault），所以命令行里 export 的值能覆盖 .env。
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default)
