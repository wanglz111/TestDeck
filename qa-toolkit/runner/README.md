# 测试执行器

本地测试用例执行工具，支持浏览器模式和原生窗模式。

## 快速启动（WSL/Linux）

### 方式一：浏览器模式（推荐）

```bash
cd /home/lucascool/TestDeck/qa-toolkit/runner
./start.sh
```

启动后：
1. 自动打开浏览器 http://127.0.0.1:8765
2. 如果浏览器没自动打开，手动访问上述地址
3. 在 Chrome 116+ 中可点击「置顶」按钮启用 PiP 浮窗

### 方式二：原生窗模式

```bash
cd /home/lucascool/TestDeck/qa-toolkit/runner
./start-desktop.sh
```

⚠️ **WSL 限制**：原生窗模式需要图形界面支持。如果你的 WSL 没有配置 X11/Wayland，推荐使用浏览器模式。

### 方式三：直接运行（调试用）

```bash
cd /home/lucascool/TestDeck/qa-toolkit/runner
python3 serve.py
```

然后手动打开浏览器访问 http://127.0.0.1:8765

## 快速启动（Windows）

### 浏览器模式
双击 `start.bat`

### 原生窗模式
双击 `start-desktop.bat`

## 功能特性

### 核心功能
- ✅ 零跳页：一屏一条用例，点击「通过/不通过」直接写飞书
- ✅ 置顶浮窗：两种方案（浏览器 PiP + pywebview 原生窗）
- ✅ 防空覆盖：三道护栏确保重提交不会丢失已填字段
- ✅ 纯键盘操作：全流程无需鼠标

### 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 标记「通过」/ 提交表单 |
| `Backspace` | 标记「不通过」 |
| `Ctrl+B` | 跳过当前用例 |
| `← →` | 上一条/下一条用例 |
| `Ctrl+Z` | 撤销（回退到上一条） |
| `Ctrl+V` | 粘贴截图（在不通过表单中） |
| `Ctrl+P` | 切换 PiP 置顶浮窗 |
| `Esc` | 关闭表单/弹窗 |
| `?` | 显示快捷键帮助 |

### 提交结果说明

**通过**：
- 写入「测试流程记录」表
- 字段：用例、结果、优先级、负责人、报告人、日期

**不通过**：
- 同时写入「测试流程记录」和「bug 报告」两张表
- 必填：说明（问题描述）
- 选填：控制台报错、截图（Ctrl+V 粘贴）

**跳过**：
- 写入「测试流程记录」表
- 结果标记为「未执行」
- 不创建 bug 报告

### 重提交机制

同一条用例可多次提交，系统会：
1. **覆盖而非追加**：相同 case_id 会更新已有记录
2. **保留已填字段**：只改结果不改截图时，截图会保留
3. **防空覆盖**：三道护栏确保不会意外清空已填内容

## 项目结构

```
qa-toolkit/runner/
├── serve.py              # HTTP 后端服务
├── app.py                # pywebview 原生窗外壳
├── lark_client.py        # 飞书 API 客户端
├── envutil.py            # 环境变量加载器
├── .env                  # 飞书配置
├── start.sh              # Linux/WSL 浏览器模式启动脚本
├── start-desktop.sh      # Linux/WSL 原生窗模式启动脚本
├── start.bat             # Windows 浏览器模式启动脚本
├── start-desktop.bat     # Windows 原生窗模式启动脚本
├── README.md             # 本文档
├── IMPLEMENTATION.md     # 实施报告
├── ACCEPTANCE.md         # 验收清单
├── data/
│   └── cases.normalized.json  # 14 条测试用例
├── static/
│   ├── index.html        # 页面结构
│   ├── style.css         # 样式
│   └── app.js            # 前端逻辑
└── shots/                # 临时截图存储（运行时）
```

## 依赖要求

### 基础依赖
- Python 3.7+
- requests（飞书 API 调用）

```bash
pip3 install requests
```

### 原生窗模式额外依赖
```bash
pip3 install pywebview
```

### 浏览器要求
- 推荐：Chrome 116+ 或 Edge 116+（支持 Document PiP）
- 最低：任何现代浏览器（不支持 PiP 则无法置顶）

## 配置说明

所有配置在 `.env` 文件中：

```ini
# 飞书国际版配置
LARK_BASE_URL=https://open.larksuite.com
LARK_APP_ID=cli_xxx
LARK_APP_SECRET=xxx

# bug 看板多维表格
LARK_BUG_APP_TOKEN=xxx
LARK_TABLE_RECORDS=tblxxx  # 测试流程记录表
LARK_TABLE_BUGS=tblxxx     # bug 报告表

# 默认值
DEFAULT_REPORTER=Max
DEFAULT_OWNER=待指派
DEFAULT_REPORTER_ID=ou_xxx  # 人员字段的 open_id
```

## 数据说明

### progress.json（自动生成）

记录测试进度和已提交记录：

```json
{
  "session": "2026-09-15",
  "reporter": "Max",
  "cursor": 0,
  "records": {
    "B-001": {
      "result": "通过",
      "record_id": "recXXXX",
      "submitted_at": 1757951234567,
      "last_fields": {
        "用例": "B-001 后台三要素登录",
        "结果": "通过",
        ...
      }
    }
  }
}
```

**关键字段**：
- `last_fields`：上次提交的字段快照，用于防空覆盖
- `record_id`：飞书记录 ID，重提交时走更新
- `bug_record_id`：bug 报告 ID（不通过时有值）

### 损坏处理

如果 `progress.json` 损坏（JSON 非法），系统会：
1. 自动备份为 `progress.json.bak`
2. 从空状态重新开始
3. 在控制台显示警告信息

## 飞书表格字段映射

### 测试流程记录表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 用例 | 文本 | case_id + 标题 |
| 结果 | 单选 | 通过/不通过/未执行 |
| 优先级 | 单选 | P0/P1/P2/P3 |
| 负责人 | 文本 | 默认「待指派」 |
| 截图 | 附件 | 可传多张 |
| 控制台 | 文本 | 控制台报错信息 |
| 报告人 | 文本 | 默认「Max」 |
| 日期 | 日期 | 提交日期（不含时分秒） |

### bug 报告表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 问题描述 | 文本 | case_id + 标题 + 说明 |
| 进展状态 | 单选 | 默认「待修复」 |
| 跟进人 | 人员 | 留空 |
| 优先级 | 单选 | 继承用例优先级（P3 提升为 P2） |
| 截图 | 附件 | 同测试流程记录 |
| 反馈人 | 人员 | 从 .env 读取 open_id |
| 反馈时间 | 日期 | 提交日期 |
| 备注 | 文本 | **必带【自动提】水印** + 控制台信息 |

⚠️ **【自动提】水印不可删除**：清理脚本依赖此标记区分自动/手动 bug。

## 故障排查

### 启动失败

**症状**：`./start.sh` 报错 `Permission denied`

**解决**：
```bash
chmod +x start.sh
./start.sh
```

---

**症状**：`ModuleNotFoundError: No module named 'requests'`

**解决**：
```bash
pip3 install requests
```

### 飞书连接失败

**症状**：健康检查失败，提示 token 无效

**解决**：
1. 检查 `.env` 中的 `LARK_APP_ID` 和 `LARK_APP_SECRET`
2. 确认是飞书国际版（open.larksuite.com），不是国内版（open.feishu.cn）
3. 访问 http://127.0.0.1:8765/api/health 查看详细错误

---

**症状**：健康检查失败，提示权限不足（code 99991663 或 99991672）

**解决**：
1. 去飞书开发者后台「权限管理」开通必需权限
2. **必须去「版本管理与发布」创建并发布新版本**
3. 权限是跟着版本生效的，不是跟着应用生效的

---

**症状**：健康检查失败，提示表不存在（code 1254040 或 1254303）

**解决**：
1. 打开多维表格
2. 右上角 ··· → 添加文档应用
3. 选择你的应用 → 给「可编辑」权限

### 提交失败

**症状**：点「通过」没反应，或提示网络错误

**解决**：
1. 确认后端服务还在运行（终端没关闭）
2. 刷新浏览器重试
3. 检查 progress.json 是否损坏（自动备份为 .bak）

---

**症状**：截图无法上传，提示文件过大

**解决**：
- 飞书限制单文件 20MB
- 压缩图片或用截图工具降低分辨率

### PiP 置顶失败

**症状**：点「置顶」按钮无反应，或提示不支持

**解决**：
- Document PiP 需要 Chrome 116+ 或 Edge 116+
- 旧版浏览器不支持，建议升级或使用原生窗模式

## 开发调试

### 查看日志

```bash
# 后端日志（终端输出）
python3 serve.py

# 前端日志（浏览器控制台）
F12 → Console
```

### 测试 API

```bash
# 健康检查
curl http://127.0.0.1:8765/api/health | python3 -m json.tool

# 会话数据
curl http://127.0.0.1:8765/api/session | python3 -m json.tool

# 提交测试（需要 multipart/form-data）
# 建议通过前端界面测试
```

### 清空进度重新开始

```bash
cd /home/lucascool/TestDeck/qa-toolkit/runner
rm progress.json
# 下次启动会从头开始
```

## 更新日志

### 2026-09-15
- ✅ 初始版本完成
- ✅ 支持浏览器模式和原生窗模式
- ✅ 实现防空覆盖三道护栏
- ✅ 支持全键盘操作
- ✅ 添加 Linux/WSL 启动脚本

## 技术支持

如遇问题：
1. 查看本文档「故障排查」章节
2. 查看 `IMPLEMENTATION.md` 了解技术细节
3. 查看 `ACCEPTANCE.md` 了解验收标准
