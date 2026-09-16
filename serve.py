#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""serve.py — 本地测试执行器后端服务

三个接口：
  GET  /api/health   验证飞书连接、token、表结构
  GET  /api/session  返回用例列表 + 本地进度
  POST /api/submit   提交测试结果（通过/不通过/未执行）

复用：
  ../scripts/lark_client.py  飞书 API 客户端
  ../scripts/envutil.py      环境变量加载
  ../data/cases.normalized.json  14 条标准化用例
  ../.env                    飞书配置
"""
from __future__ import annotations

import json
import os
import sys
import time
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from threading import Thread

# 导入本地模块
_ROOT = Path(__file__).parent

from envutil import load_dotenv, env  # noqa: E402
from lark_client import (  # noqa: E402
    LarkClient, LarkError, f_text, f_select, f_date, f_attachment, f_user
)

# 加载环境变量
load_dotenv(_ROOT / ".env")

# 配置
PORT = 8765
CASES_PATH = _ROOT / "data" / "cases.normalized.json"
PROGRESS_PATH = _ROOT / "progress.json"
SHOTS_DIR = _ROOT / "shots"

DEFAULT_REPORTER = env("DEFAULT_REPORTER", "Max")
DEFAULT_OWNER = env("DEFAULT_OWNER", "待指派")
DEFAULT_REPORTER_ID = env("DEFAULT_REPORTER_ID", "")

# 飞书客户端
lark = LarkClient(
    app_id=env("LARK_APP_ID"),
    app_secret=env("LARK_APP_SECRET"),
    base_url=env("LARK_BASE_URL", "https://open.larksuite.com"),
    verbose=True
)

BUG_APP_TOKEN = env("LARK_BUG_APP_TOKEN")
TABLE_RECORDS = env("LARK_TABLE_RECORDS")
TABLE_BUGS = env("LARK_TABLE_BUGS")


# ================================================================
# 日期处理：只到日，传当天正午毫秒
# ================================================================

def ts_date_ms(d=None):
    """日期字段（只到日）用的毫秒。取当天正午，不取当前时刻。
    
    为什么是正午：日期字段存的是瞬时时间戳，显示时按 base 的时区渲染。
    传当前时刻的话，本地深夜或凌晨提交时，在 base 时区里可能落到前一天/后一天。
    正午离两个日界各 12 小时，能吸收 ±12h 的时区差。
    """
    d = (d or datetime.now()).replace(hour=12, minute=0, second=0, microsecond=0)
    return int(d.timestamp() * 1000)


# ================================================================
# 数据加载
# ================================================================

def load_cases():
    """加载标准化用例"""
    if not CASES_PATH.exists():
        return []
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return data.get("cases", [])


def load_progress():
    """加载本地进度"""
    if not PROGRESS_PATH.exists():
        return {
            "session": datetime.now().strftime("%Y-%m-%d"),
            "reporter": DEFAULT_REPORTER,
            "cursor": 0,
            "records": {}
        }
    
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except (ValueError, IOError) as e:
        # JSON 损坏，备份后重置
        backup = PROGRESS_PATH.with_suffix(".json.bak")
        PROGRESS_PATH.rename(backup)
        print(f"⚠️  progress.json 损坏，已备份到 {backup.name}，从空状态起")
        return {
            "session": datetime.now().strftime("%Y-%m-%d"),
            "reporter": DEFAULT_REPORTER,
            "cursor": 0,
            "records": {}
        }


def save_progress(prog):
    """保存进度"""
    PROGRESS_PATH.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")


# ================================================================
# API: /api/health
# ================================================================

def handle_health():
    """健康检查：验证 token、两张表、字段名"""
    result = {
        "ok": True,
        "token": False,
        "base": BUG_APP_TOKEN,
        "tables": {},
        "reporter": DEFAULT_REPORTER,
        "dry_run": False
    }
    
    # 1. 验证 token
    try:
        lark.token()
        result["token"] = True
    except LarkError as e:
        return {
            "ok": False,
            "step": "token",
            "error": str(e),
            "hint": "检查 .env 的 LARK_APP_ID / LARK_APP_SECRET 有没有抄错"
        }
    
    # 2. 验证测试流程记录表
    try:
        fields = lark.list_fields(BUG_APP_TOKEN, TABLE_RECORDS)
        field_names = {f["field_name"] for f in fields}
        required = {"用例", "结果", "优先级", "负责人", "截图", "控制台", "报告人", "日期"}
        missing = required - field_names
        
        if missing:
            return {
                "ok": False,
                "step": "records",
                "error": f"测试流程记录表缺少字段：{', '.join(missing)}",
                "hint": "去飞书表里检查列名，或重新建表"
            }
        
        result["tables"]["records"] = {"ok": True, "rows": len(fields)}
    except LarkError as e:
        return {
            "ok": False,
            "step": "records",
            "error": str(e),
            "hint": "应用没被加进这张多维表格 → 打开表格 → 右上角 ··· → 添加文档应用"
        }
    
    # 3. 验证 bug 报告表
    try:
        fields = lark.list_fields(BUG_APP_TOKEN, TABLE_BUGS)
        field_names = {f["field_name"] for f in fields}
        required = {"问题描述", "进展状态", "跟进人", "优先级", "截图", "反馈人", "反馈时间", "备注"}
        missing = required - field_names
        
        if missing:
            return {
                "ok": False,
                "step": "bugs",
                "error": f"bug 报告表缺少字段：{', '.join(missing)}",
                "hint": "去飞书表里检查列名，或重新建表"
            }
        
        result["tables"]["bugs"] = {"ok": True, "rows": len(fields)}
    except LarkError as e:
        return {
            "ok": False,
            "step": "bugs",
            "error": str(e),
            "hint": "应用没被加进这张多维表格 → 打开表格 → 右上角 ··· → 添加文档应用"
        }
    
    return result


# ================================================================
# API: /api/session
# ================================================================

def handle_session():
    """返回用例列表 + 本地进度"""
    cases = load_cases()
    progress = load_progress()
    
    return {
        "cases": cases,
        "progress": progress,
        "reporter": DEFAULT_REPORTER,
        "owner": DEFAULT_OWNER,
        "table": "测试流程记录",
        "dry_run": False
    }


# ================================================================
# API: /api/submit
# ================================================================

def handle_submit(form_data, files):
    """提交测试结果
    
    form_data: {
        'case_id': ['B-003'],
        'result': ['通过'],
        'note': ['...'],
        'console': ['...'],
        'touched': ['["console"]']
    }
    files: [('images', filename, data), ...]
    """
    # 1. 解析字段
    case_id = form_data.get('case_id', [''])[0].strip()
    result = form_data.get('result', [''])[0].strip()
    note = form_data.get('note', [''])[0].strip()
    console_text = form_data.get('console', [''])[0].strip()
    touched_raw = form_data.get('touched', ['[]'])[0]
    
    try:
        touched = json.loads(touched_raw)
    except:
        touched = []
    
    if not case_id or not result:
        return {"ok": False, "error": "缺少 case_id 或 result"}
    
    if result not in ("通过", "不通过", "未执行"):
        return {"ok": False, "error": f"result 非法：{result}"}
    
    if result == "不通过" and not note:
        return {"ok": False, "error": "不通过时必须填写说明"}
    
    # 2. 加载用例和进度
    cases = load_cases()
    case = next((c for c in cases if c["id"] == case_id), None)
    if not case:
        return {"ok": False, "error": f"用例 {case_id} 不存在"}
    
    progress = load_progress()
    old_record = progress["records"].get(case_id, {})
    last_fields = old_record.get("last_fields", {})
    
    # 3. 上传截图
    file_tokens = []
    SHOTS_DIR.mkdir(exist_ok=True)
    
    for field_name, filename, data in files:
        if field_name != 'images':
            continue
        
        # 检查大小
        if len(data) > 20 * 1024 * 1024:
            return {"ok": False, "error": f"截图 {filename} 超过 20MB"}
        
        # 保存临时文件
        shot_path = SHOTS_DIR / filename
        shot_path.write_bytes(data)
        
        try:
            token = lark.upload_media(shot_path, BUG_APP_TOKEN, "bitable_image")
            file_tokens.append(token)
        except LarkError as e:
            return {"ok": False, "step": "upload", "error": str(e)}
        finally:
            shot_path.unlink(missing_ok=True)
    
    # 如果本次没传图，复用旧图
    if not file_tokens and old_record.get("images"):
        file_tokens = [img["file_token"] for img in old_record["images"]]
    
    # 4. 字段级合并（防空覆盖核心）
    new_fields = {
        "用例": f_text(f"{case['id']} {case['title']}"),
        "结果": f_select(result),
        "优先级": f_select(case.get("priority", "P2")),
        "负责人": f_text(DEFAULT_OWNER),
        "报告人": f_text(DEFAULT_REPORTER),
        "日期": f_date(ts_date_ms())
    }
    
    # 截图：本次有传 → 更新；没传 → 不放进请求体（保留旧值）
    if files:
        new_fields["截图"] = f_attachment(file_tokens)
    
    # 控制台：有值 → 更新；空且上次有值且不在 touched → 不放进请求体
    if console_text:
        new_fields["控制台"] = f_text(console_text)
    elif "控制台" in touched:
        new_fields["控制台"] = f_text("")  # 显式清空
    # 否则不放进请求体，保留旧值
    
    # 本地比对护栏
    for key, new_val in list(new_fields.items()):
        old_val = last_fields.get(key)
        if old_val and not new_val and key not in touched:
            # 上次有值 → 这次空 且不在 touched
            if key not in ("用例", "结果", "优先级", "负责人", "报告人", "日期"):  # 必填字段跳过
                return {
                    "ok": False,
                    "error": f"字段 {key} 上次有值，这次为空且未在 touched 中声明",
                    "hint": "可能是合并逻辑 bug，拒绝提交防止空覆盖"
                }
    
    # 5. 写测试流程记录
    record_id = old_record.get("record_id")
    
    try:
        if record_id:
            # 更新已有记录
            # 云端比对护栏（简化版：仅检查记录是否存在）
            try:
                records = lark.list_records(BUG_APP_TOKEN, TABLE_RECORDS)
                exists = any(r["record_id"] == record_id for r in records)
                if not exists:
                    print(f"⚠️  record_id {record_id} 在云端不存在，将新建记录")
                    record_id = None
            except LarkError:
                pass  # 云端比对失败不阻塞
            
            if record_id:
                lark.update_record(BUG_APP_TOKEN, TABLE_RECORDS, record_id, new_fields)
                print(f"✓ 更新测试流程记录 {record_id}")
        
        if not record_id:
            # 新建记录
            record_id = lark.create_record(BUG_APP_TOKEN, TABLE_RECORDS, new_fields)
            print(f"✓ 新建测试流程记录 {record_id}")
        
        time.sleep(0.4)  # 飞书不支持并发写
        
    except LarkError as e:
        return {"ok": False, "step": "records", "error": str(e)}
    
    # 6. 若不通过，写 bug 报告
    bug_record_id = old_record.get("bug_record_id")
    
    if result == "不通过":
        bug_fields = {
            "问题描述": f_text(f"{case['id']} {case['title']}\n{note}"),
            "进展状态": f_select("待修复"),
            "优先级": f_select("P2" if case.get("priority") == "P3" else case.get("priority", "P2")),
            "反馈时间": f_date(ts_date_ms()),
            "备注": f_text(f"【自动提】由用例 {case_id} 提交（结果：{result}）\n{console_text}")
        }
        
        if files:
            bug_fields["截图"] = f_attachment(file_tokens)
        
        if DEFAULT_REPORTER_ID:
            bug_fields["反馈人"] = f_user([DEFAULT_REPORTER_ID])
        
        try:
            if bug_record_id:
                lark.update_record(BUG_APP_TOKEN, TABLE_BUGS, bug_record_id, bug_fields)
                print(f"✓ 更新 bug 报告 {bug_record_id}")
            else:
                bug_record_id = lark.create_record(BUG_APP_TOKEN, TABLE_BUGS, bug_fields)
                print(f"✓ 新建 bug 报告 {bug_record_id}")
            
            time.sleep(0.4)
            
        except LarkError as e:
            # bug 报告失败不阻塞，返回 partial
            return {
                "ok": True,
                "record_id": record_id,
                "bug_record_id": None,
                "submitted_at": int(time.time() * 1000),
                "partial": {"record_id": record_id, "bug_record_id": None},
                "warning": f"测试流程记录已写入，但 bug 报告失败：{e}"
            }
    
    # 7. 更新本地进度
    progress["records"][case_id] = {
        "result": result,
        "record_id": record_id,
        "bug_record_id": bug_record_id,
        "submitted_at": int(time.time() * 1000),
        "note": note,
        "console": console_text,
        "images": [{"name": f"shot-{i}.png", "file_token": t} for i, t in enumerate(file_tokens)],
        "last_fields": new_fields
    }
    
    save_progress(progress)
    
    return {
        "ok": True,
        "record_id": record_id,
        "bug_record_id": bug_record_id,
        "submitted_at": int(time.time() * 1000),
        "dry_run": False
    }


# ================================================================
# HTTP 服务器
# ================================================================

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """静音日志，只打印关键信息"""
        pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        # 静态文件
        if parsed.path == "/" or parsed.path == "/index.html":
            self.serve_file("static/index.html", "text/html")
        elif parsed.path == "/style.css":
            self.serve_file("static/style.css", "text/css")
        elif parsed.path == "/app.js":
            self.serve_file("static/app.js", "application/javascript")
        
        # API
        elif parsed.path == "/api/health":
            result = handle_health()
            self.send_json(result, 200 if result["ok"] else 503)
        
        elif parsed.path == "/api/session":
            result = handle_session()
            self.send_json(result)
        
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == "/api/submit":
            # 解析 multipart/form-data
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self.send_json({"ok": False, "error": "需要 multipart/form-data"}, 400)
                return
            
            boundary = content_type.split("boundary=")[1].encode()
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            
            form_data, files = self.parse_multipart(body, boundary)
            result = handle_submit(form_data, files)
            self.send_json(result, 200 if result.get("ok") else 400)
        else:
            self.send_error(404)
    
    def serve_file(self, rel_path, content_type):
        file_path = Path(__file__).parent / rel_path
        if not file_path.exists():
            self.send_error(404)
            return
        
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)
    
    def send_json(self, data, status=200):
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)
    
    def parse_multipart(self, body, boundary):
        """简化的 multipart 解析"""
        parts = body.split(b'--' + boundary)
        form_data = {}
        files = []
        
        for part in parts[1:-1]:
            if not part or part == b'--\r\n':
                continue
            
            # 分离 headers 和 content
            if b'\r\n\r\n' in part:
                headers_raw, content = part.split(b'\r\n\r\n', 1)
            else:
                continue
            
            content = content.rstrip(b'\r\n')
            headers = headers_raw.decode('utf-8', errors='ignore')
            
            # 解析 Content-Disposition
            name = None
            filename = None
            for line in headers.split('\r\n'):
                if line.startswith('Content-Disposition:'):
                    if 'name="' in line:
                        name = line.split('name="')[1].split('"')[0]
                    if 'filename="' in line:
                        filename = line.split('filename="')[1].split('"')[0]
            
            if not name:
                continue
            
            if filename:
                # 文件
                files.append((name, filename, content))
            else:
                # 表单字段
                value = content.decode('utf-8', errors='ignore')
                if name in form_data:
                    form_data[name].append(value)
                else:
                    form_data[name] = [value]
        
        return form_data, files


def serve_in_thread():
    """在线程中启动服务器（供 pywebview 调用）"""
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    print(f"✓ 服务器启动在 http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    print("=" * 60)
    print("本地测试执行器 — 后端服务")
    print("=" * 60)
    print()
    
    # 启动服务器
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    print(f"✓ 服务器启动在 http://127.0.0.1:{PORT}")
    print()
    
    # 自动打开浏览器
    try:
        webbrowser.open(f'http://127.0.0.1:{PORT}')
        print("✓ 浏览器已打开")
    except:
        print("⚠️  无法自动打开浏览器，请手动访问上述地址")
    
    print()
    print("按 Ctrl+C 停止服务")
    print()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n✓ 服务器已停止")
