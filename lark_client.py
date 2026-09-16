#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lark_client.py — Lark 国际版（open.larksuite.com）多维表格写入客户端

只干三件事：拿 token、传素材换 file_token、批量写记录。
依赖：requests（唯一第三方依赖）

⚠️ 两条必须记住的写入约束（官方文档口径）：
  1. 附件字段不能直接塞文件 —— 必须先「上传素材」拿到 file_token，再把 file_token 写进记录；
     且 file_token 只在当前这张多维表格里有效，换表要重传。
  2. 单次批量上限 500 条；同一张数据表不支持并发写 —— 必须串行 + 留间隔。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import requests

DEFAULT_BASE = "https://open.larksuite.com"
BATCH_LIMIT = 500

# 多维表格的两种 URL 形态：
#   …/base/XXXXXXXX?table=tbl…   → 普通多维表格，XXXXXXXX 就是 app_token
#   …/wiki/XXXXXXXX?table=tbl…   → **放在知识库里**的多维表格
#                                   XXXXXXXX 是知识库节点 token(node_token)，**不是 app_token**
#                                   必须先调 wiki/v2/spaces/get_node 换成 obj_token
_BITABLE_URL_RE = re.compile(r"/(base|wiki)/([A-Za-z0-9_-]+)")


def parse_bitable_url(value: str) -> tuple[str, str]:
    """从多维表格 URL（或裸 token）里抠出 (kind, token)。

    kind 取值：
      "base" → 普通多维表格，token 直接就是 app_token
      "wiki" → 知识库里的多维表格，token 是 node_token，需要再解析一次

    直接传裸 token 时按 "base" 处理（兼容旧用法，此时 token 本身就是 app_token）。
    """
    m = _BITABLE_URL_RE.search(value or "")
    if m:
        return m.group(1), m.group(2)
    return "base", (value or "").strip()


class LarkError(RuntimeError):
    pass


# ---------------------------------------------------------------- 错误码翻译
# Lark 报错只给一个数字，新手基本看不懂。这里翻译成人话 + 下一步动作。
# 遇到没收录的 code，把完整报错发出来，加一行就行。
_ERROR_HINTS: dict[int, str] = {
    10003: "app_id / app_secret 不对，或者平台填反了 —— "
           "Lark 国际版是 open.larksuite.com，飞书国内版是 open.feishu.cn，别搞混",
    99991661: "token 无效或已过期 —— 检查 app_id / app_secret 有没有抄错",
    99991663: "【新权限没生效】去开发者后台「权限管理」开通，然后**必须去"
              "「版本管理与发布」发一个新版本** —— 已有旧版本不算，"
              "权限是跟着版本生效的，不是跟着应用生效的",
    99991672: "【权限没生效 —— 不是没开通】开发者后台「权限管理」里显示『已开通』"
              "只说明**配置已保存**，不等于生效。真正生效的开关是**发布新版本**："
              "看应用名旁边有没有写『待发布 / 当前修改尚未发布』——有的话去"
              "「版本管理与发布」创建并发布一个新版本（测试企业免审，提交即生效）。"
              "生效后那里会变成『当前修改均已发布』",
    1254005: "app_token 不对 —— 应该是多维表格 URL 里 /base/ 后面那一串",
    1254040: "【应用没被加进这张多维表格】打开表格 → 右上角 ··· → 添加文档应用 → "
             "选你的应用 → 给「可编辑」",
    1254303: "数据表不存在，或应用没有这张表的访问权（同 1254040 的办法处理）",
    1254006: "字段不存在 —— 字段名写错了？",
    1061043: "文件超过大小限制（全量上传上限 20MB）",
    1062009: "size 参数和实际文件大小对不上",
}


def explain(code, msg: str = "") -> str:
    """把 Lark 错误码翻译成「现象 + 怎么办」。"""
    hint = _ERROR_HINTS.get(code)
    return f"{msg}｜{hint}" if hint else str(msg)


# ---------------------------------------------------------------- 字段值构造
# Lark 多维表格各类字段的写入格式都不一样，这里统一收口，避免调用处记混。

def f_text(v) -> str:
    """文本 / 电话 / 条码"""
    return "" if v is None else str(v)


def f_select(v):
    """单选：传字符串。选项不存在时 Lark 会自动新建。"""
    return None if v in (None, "") else str(v)


def f_multi(v):
    """多选：传字符串数组"""
    if not v:
        return []
    return [str(x) for x in (v if isinstance(v, (list, tuple)) else [v])]


def f_number(v):
    """数字 / 进度 / 货币：传数值，不是字符串"""
    if v in (None, ""):
        return None
    return float(v) if isinstance(v, str) and "." in v else int(v)


def f_date(ts_ms: int):
    """日期：传毫秒时间戳（不是秒！）"""
    return int(ts_ms)


def f_attachment(file_tokens):
    """附件：传 [{file_token: ...}]，token 必须先由 upload_media 拿到"""
    return [{"file_token": t} for t in (file_tokens or [])]


def f_user(ids):
    """人员：传 open_id 数组（形如 ou_xxxx）。**不能传姓名或邮箱。**

    open_id 是「应用视角」的 id —— 用本应用的 token 读出来的 ou_ 值，
    才能用本应用的 token 写回去。跨应用拿到的不通用。
    """
    if not ids:
        return None
    return [{"id": i} for i in (ids if isinstance(ids, (list, tuple)) else [ids])]


def f_url(text: str, link: str):
    """超链接"""
    return {"text": text, "link": link}


def f_checkbox(v):
    return bool(v)


# ---------------------------------------------------------------- 客户端

class LarkClient:
    def __init__(self, app_id: str, app_secret: str, base_url: str = DEFAULT_BASE,
                 timeout: int = 30, verbose: bool = False):
        if not app_id or not app_secret:
            raise LarkError("缺 app_id / app_secret，请填 .env")
        self.app_id = app_id
        self.app_secret = app_secret
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.verbose = verbose
        self._token = None
        self._token_exp = 0.0
        self.sess = requests.Session()

    # -- token ---------------------------------------------------------
    def token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        r = self.sess.post(
            f"{self.base}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=self.timeout,
        )
        data = self._unwrap(r)
        self._token = data["tenant_access_token"]
        self._token_exp = time.time() + int(data.get("expire", 7200))
        if self.verbose:
            print(f"  [lark] token 已刷新，有效期 {data.get('expire')}s")
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}

    @staticmethod
    def _unwrap(r: requests.Response) -> dict:
        try:
            body = r.json()
        except ValueError:
            raise LarkError(f"HTTP {r.status_code} 非 JSON 响应：{r.text[:200]}")
        if body.get("code") not in (0, None):
            log_id = "-"
            err = body.get("error")
            if isinstance(err, dict):
                log_id = err.get("log_id", "-")
            code = body.get("code")
            raise LarkError(f"Lark 报错 code={code}｜{explain(code, body.get('msg', ''))} "
                            f"(log_id={log_id})")
        return body.get("data", body)

    # -- 素材上传 ------------------------------------------------------
    def upload_media(self, file_path: str | Path, parent_node: str,
                     parent_type: str = "bitable_image") -> str:
        """上传一个文件，返回可写进当前多维表格的 file_token。"""
        p = Path(file_path)
        size = p.stat().st_size
        with p.open("rb") as fh:
            r = self.sess.post(
                f"{self.base}/open-apis/drive/v1/medias/upload_all",
                headers=self._headers(),
                data={
                    "file_name": p.name,
                    "parent_type": parent_type,   # bitable_image / bitable_file
                    "parent_node": parent_node,   # 多维表格的 app_token
                    "size": str(size),
                },
                files={"file": (p.name, fh, _guess_mime(p))},
                timeout=max(self.timeout, 60),
            )
        data = self._unwrap(r)
        if self.verbose:
            print(f"  [lark] 上传 {p.name} → {data.get('file_token')}")
        return data["file_token"]

    # -- 记录读写 ------------------------------------------------------
    def create_record(self, app_token: str, table_id: str, fields: dict) -> str:
        r = self.sess.post(
            f"{self.base}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            headers=self._headers(), json={"fields": fields}, timeout=self.timeout,
        )
        return self._unwrap(r)["record"]["record_id"]

    def update_record(self, app_token: str, table_id: str, record_id: str, fields: dict) -> bool:
        r = self.sess.put(
            f"{self.base}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            headers=self._headers(), json={"fields": fields}, timeout=self.timeout,
        )
        self._unwrap(r)
        return True

    def batch_create(self, app_token: str, table_id: str, rows: list[dict],
                     batch: int = BATCH_LIMIT, sleep: float = 0.6) -> list[str]:
        """批量新增记录。串行分批 + 每批之间留间隔（同表不支持并发写）。"""
        ids: list[str] = []
        for i in range(0, len(rows), batch):
            chunk = [{"fields": f} for f in rows[i:i + batch]]
            r = self.sess.post(
                f"{self.base}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
                headers=self._headers(), json={"records": chunk}, timeout=max(self.timeout, 60),
            )
            data = self._unwrap(r)
            got = [rec["record_id"] for rec in data.get("records", [])]
            ids.extend(got)
            if self.verbose:
                print(f"  [lark] 写入 {len(got)} 条（累计 {len(ids)}/{len(rows)}）")
            if i + batch < len(rows):
                time.sleep(sleep)
        return ids

    def list_records(self, app_token: str, table_id: str,
                     page_size: int = 500) -> list[dict]:
        """列出表里已有的记录（只取 record_id 也够用，用来做清空/去重）。"""
        out, page = [], None
        while True:
            params: dict = {"page_size": min(page_size, 500)}
            if page:
                params["page_token"] = page
            r = self.sess.get(
                f"{self.base}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                headers=self._headers(), params=params, timeout=self.timeout,
            )
            data = self._unwrap(r)
            out.extend(data.get("items", []))
            if not data.get("has_more"):
                return out
            page = data.get("page_token")

    def batch_delete(self, app_token: str, table_id: str, record_ids: list[str],
                     batch: int = BATCH_LIMIT, sleep: float = 0.6) -> int:
        """批量删除记录，返回删掉的条数。"""
        n = 0
        for i in range(0, len(record_ids), batch):
            r = self.sess.post(
                f"{self.base}/open-apis/bitable/v1/apps/{app_token}"
                f"/tables/{table_id}/records/batch_delete",
                headers=self._headers(),
                json={"records": record_ids[i:i + batch]},
                timeout=max(self.timeout, 60),
            )
            self._unwrap(r)
            n += len(record_ids[i:i + batch])
            if self.verbose:
                print(f"  [lark] 删除 {n}/{len(record_ids)} 条")
            if i + batch < len(record_ids):
                time.sleep(sleep)
        return n

    def list_fields(self, app_token: str, table_id: str) -> list[dict]:
        out, page = [], None
        while True:
            params = {"page_size": 100}
            if page:
                params["page_token"] = page
            r = self.sess.get(
                f"{self.base}/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                headers=self._headers(), params=params, timeout=self.timeout,
            )
            data = self._unwrap(r)
            out.extend(data.get("items", []))
            if not data.get("has_more"):
                return out
            page = data.get("page_token")


_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf",
         ".txt": "text/plain", ".mp4": "video/mp4", ".log": "text/plain"}


def _guess_mime(p: Path) -> str:
    return _MIME.get(p.suffix.lower(), "application/octet-stream")


def ts_ms(dt=None) -> int:
    """当前时间（或指定时间）的毫秒时间戳 —— 日期字段要毫秒。"""
    from datetime import datetime
    dt = dt or datetime.now()
    return int(dt.timestamp() * 1000)
