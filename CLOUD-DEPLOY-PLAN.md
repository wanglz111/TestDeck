# TestDeck 云化部署计划

> **目标**：将 QA 测试执行器改造为云端多用户平台，支持测试用例上传、进度同步、团队协作
> 
> **预计工时**：16-20 小时（2-3 天）
> 
> **交付物**：Docker Compose 一键部署包 + 完整的云端测试平台

---

## 📋 Phase 1: 数据库设计与迁移（2h）

### 1.1 数据库表结构设计

```sql
-- users: 用户表
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'tester',  -- admin/tester
    created_at TIMESTAMP DEFAULT NOW()
);

-- test_suites: 测试用例集
CREATE TABLE test_suites (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    version VARCHAR(20),
    total_cases INTEGER DEFAULT 0,
    uploaded_by INTEGER REFERENCES users(id),
    uploaded_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- test_cases: 测试用例
CREATE TABLE test_cases (
    id SERIAL PRIMARY KEY,
    suite_id INTEGER REFERENCES test_suites(id) ON DELETE CASCADE,
    case_id VARCHAR(20) UNIQUE NOT NULL,
    execution_order INTEGER,
    title VARCHAR(500),
    module VARCHAR(100),
    端 VARCHAR(20),
    priority VARCHAR(10),
    case_type VARCHAR(50),
    layer VARCHAR(50),
    requirement_ref TEXT,
    requirement_level VARCHAR(50),
    requirement_note TEXT,
    blocking_item TEXT,
    precondition TEXT,
    test_data TEXT,
    steps TEXT,
    expected TEXT,
    batch INTEGER,
    raw_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_case_suite ON test_cases(suite_id);
CREATE INDEX idx_case_layer ON test_cases(layer);
CREATE INDEX idx_case_batch ON test_cases(batch);

-- test_executions: 执行记录
CREATE TABLE test_executions (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(20) REFERENCES test_cases(case_id),
    user_id INTEGER REFERENCES users(id),
    status VARCHAR(20) NOT NULL,  -- pass/fail/skip
    executed_at TIMESTAMP DEFAULT NOW(),
    note TEXT,
    screenshot_urls TEXT[]
);

CREATE INDEX idx_exec_case ON test_executions(case_id);
CREATE INDEX idx_exec_user ON test_executions(user_id);
CREATE INDEX idx_exec_time ON test_executions(executed_at DESC);

-- progress_snapshots: 进度快照（用于恢复）
CREATE TABLE progress_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    suite_id INTEGER REFERENCES test_suites(id),
    progress_data JSONB,
    saved_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_progress_user_suite ON progress_snapshots(user_id, suite_id);
```

### 1.2 数据迁移脚本

**文件**：`qa-toolkit/runner/init_db.py`

- 读取现有 `cases.normalized.json`
- 转换并导入到 PostgreSQL
- 创建默认管理员账号

**检查点**：
- [ ] 表结构创建成功
- [ ] 现有测试用例成功导入
- [ ] 管理员账号可登录

---

## 📋 Phase 2: 后端 API 开发（6h）

### 2.1 依赖更新

**文件**：`qa-toolkit/runner/requirements.txt`

新增：
```
flask-sqlalchemy==3.0.5
flask-jwt-extended==4.5.2
psycopg2-binary==2.9.7
bcrypt==4.0.1
python-dotenv==1.0.0
gunicorn==21.2.0
pandas==2.1.0  # CSV解析
```

### 2.2 核心 API 接口

**文件**：`qa-toolkit/runner/api.py`（新建）

#### 2.2.1 认证模块
- `POST /api/auth/login` - 用户登录，返回 JWT token
- `POST /api/auth/register` - 注册新用户（仅管理员）
- `GET /api/auth/me` - 获取当前用户信息

#### 2.2.2 测试用例管理
- `GET /api/suites` - 获取测试用例集列表
- `POST /api/suites/upload` - 上传测试用例（CSV/JSON）
  - 支持格式：CSV（从过程测试目录）、JSON（现有格式）
  - 自动解析字段映射
  - 返回导入结果统计
- `GET /api/suites/:id/cases` - 获取指定用例集的所有用例
  - 支持筛选：`?layer=冒烟层&batch=1&module=登录`
  - 支持分页：`?page=1&per_page=50`
- `GET /api/cases/:case_id` - 获取单条用例详情

#### 2.2.3 执行记录
- `POST /api/executions` - 保存执行结果
  ```json
  {
    "case_id": "C-001",
    "status": "pass",
    "note": "测试通过",
    "screenshot_urls": ["https://..."]
  }
  ```
- `GET /api/executions/progress/:suite_id` - 获取当前用户的进度
  - 返回：已测/未测/通过/失败数量 + 每条用例最新状态
- `GET /api/executions/history/:case_id` - 获取某用例的执行历史

#### 2.2.4 统计分析（Phase 3 可选）
- `GET /api/stats/suite/:id` - 用例集统计（通过率、覆盖率）
- `GET /api/stats/user/:id` - 用户测试统计

### 2.3 CSV 解析器

**文件**：`qa-toolkit/runner/csv_parser.py`（新建）

- 自动识别字段映射（中文列名 → 数据库字段）
- 处理批次信息（从文件名或内容推断）
- 数据清洗和验证

**检查点**：
- [ ] 所有 API 接口测试通过
- [ ] CSV 上传成功导入数据库
- [ ] JWT 认证正常工作
- [ ] 执行记录保存和读取正确

---

## 📋 Phase 3: 前端改造（5h）

### 3.1 登录页

**文件**：`qa-toolkit/runner/static/login.html`（新建）

- 用户名 + 密码登录
- JWT token 保存到 localStorage
- 登录失败提示

### 3.2 主应用改造

**文件**：`qa-toolkit/runner/static/app.js`

#### 3.2.1 认证封装
```javascript
// 1. 检查登录状态
if (!localStorage.getItem('token')) {
    window.location.href = '/login.html';
}

// 2. API 请求封装（自动带 token）
async function apiRequest(url, options = {}) {
    const token = localStorage.getItem('token');
    const res = await fetch(url, {
        ...options,
        headers: {
            ...options.headers,
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        }
    });
    if (res.status === 401) {
        // token 过期，跳转登录
        localStorage.removeItem('token');
        window.location.href = '/login.html';
    }
    return res;
}
```

#### 3.2.2 数据加载改造
- 从 `/api/suites` 获取可用的测试用例集
- 顶部增加下拉选择：选择用例集 + 筛选条件
- 从 `/api/suites/:id/cases` 加载用例（替代本地 JSON）
- 从 `/api/executions/progress/:suite_id` 恢复进度

#### 3.2.3 结果保存改造
- 每次标记（通过/失败/跳过）调用 `/api/executions`
- 截图上传保持飞书（或改为上传到服务器）
- 添加防抖（1秒内多次操作只提交最后一次）

#### 3.2.4 筛选面板
```html
<div class="filters">
    <select id="suite-select">
        <option value="">选择测试用例集...</option>
    </select>
    <select id="layer-filter">
        <option value="">全部分层</option>
        <option value="冒烟层">冒烟层</option>
        <option value="核心层">核心层</option>
        <option value="完整层">完整层</option>
    </select>
    <select id="batch-filter">
        <option value="">全部批次</option>
        <option value="1">第一批</option>
        <option value="2">第二批</option>
        <!-- ... -->
    </select>
    <select id="module-filter">
        <option value="">全部模块</option>
        <!-- 动态生成 -->
    </select>
    <button id="reset-filters">重置</button>
</div>
```

### 3.3 管理后台页面（可选）

**文件**：`qa-toolkit/runner/static/admin.html`（新建）

- 上传测试用例（拖拽CSV文件）
- 用户管理（创建/删除用户）
- 用例集管理（查看统计、删除旧版本）

**检查点**：
- [ ] 登录流程完整
- [ ] 用例加载和筛选正常
- [ ] 执行结果保存到数据库
- [ ] 刷新页面进度正确恢复
- [ ] 多设备登录同一账号进度同步

---

## 📋 Phase 4: Docker 容器化（3h）

### 4.1 Dockerfile

**文件**：`qa-toolkit/runner/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建上传目录
RUN mkdir -p /app/uploads

EXPOSE 8080

# 使用 gunicorn 运行（生产环境）
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "4", "--timeout", "120", "app:app"]
```

### 4.2 Docker Compose

**文件**：`docker-compose.yml`

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: testdeck-db
    environment:
      POSTGRES_DB: testdeck
      POSTGRES_USER: testdeck
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"  # 开发时可以外部连接
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U testdeck"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build: ./qa-toolkit/runner
    container_name: testdeck-app
    environment:
      DATABASE_URL: postgresql://testdeck:${DB_PASSWORD}@postgres:5432/testdeck
      JWT_SECRET_KEY: ${JWT_SECRET}
      FLASK_ENV: production
    volumes:
      - ./uploads:/app/uploads
      - ./qa-toolkit/runner/.env:/app/.env
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
    driver: local
```

### 4.3 环境变量

**文件**：`.env.production`（部署时创建）

```bash
DB_PASSWORD=<生成的强密码>
JWT_SECRET=<生成的随机密钥>

# 飞书配置（保留截图上传功能）
FEISHU_APP_ID=xxx
FEISHU_APP_SECRET=xxx
FEISHU_BITABLE_APP_TOKEN=xxx
FEISHU_BITABLE_TABLE_ID=xxx
```

### 4.4 初始化脚本

**文件**：`init.sql`

```sql
-- 自动创建表结构（从 Phase 1 的 SQL）
-- 自动创建默认管理员
INSERT INTO users (username, password_hash, role) 
VALUES ('admin', '$2b$12$...', 'admin');
```

**检查点**：
- [ ] `docker-compose build` 构建成功
- [ ] `docker-compose up` 启动成功
- [ ] 容器间网络连通
- [ ] 数据库初始化完成
- [ ] 后端健康检查通过

---

## 📋 Phase 5: Nginx 配置与部署（2h）

### 5.1 Nginx 配置

**文件**：`/etc/nginx/sites-available/testdeck.conf`

```nginx
upstream testdeck_backend {
    server 127.0.0.1:8080;
}

server {
    listen 80;
    server_name <你的域名>;
    
    # 强制跳转 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name <你的域名>;
    
    # SSL 证书（你提供或使用 Let's Encrypt）
    ssl_certificate /etc/nginx/ssl/<你的域名>.crt;
    ssl_certificate_key /etc/nginx/ssl/<你的域名>.key;
    
    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # 安全头
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    # 日志
    access_log /var/log/nginx/testdeck_access.log;
    error_log /var/log/nginx/testdeck_error.log;
    
    # 上传大小限制（CSV文件可能较大）
    client_max_body_size 50M;
    
    # API 代理
    location /api/ {
        proxy_pass http://testdeck_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # 超时设置（导入大CSV时可能耗时较长）
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
    
    # 静态文件
    location / {
        proxy_pass http://testdeck_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # 上传文件
    location /uploads/ {
        alias /home/<user>/TestDeck/uploads/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 5.2 部署脚本

**文件**：`deploy.sh`

```bash
#!/bin/bash
set -e

echo "🚀 开始部署 TestDeck..."

# 1. 拉取最新代码（如果是Git仓库）
if [ -d ".git" ]; then
    echo "📥 拉取最新代码..."
    git pull origin main
fi

# 2. 生成环境变量（首次部署）
if [ ! -f ".env.production" ]; then
    echo "🔑 生成环境变量..."
    DB_PASSWORD=$(openssl rand -base64 32)
    JWT_SECRET=$(openssl rand -base64 64)
    cat > .env.production <<EOF
DB_PASSWORD=${DB_PASSWORD}
JWT_SECRET=${JWT_SECRET}
EOF
    echo "✅ 环境变量已生成，请编辑 .env.production 补充飞书配置"
    exit 0
fi

# 3. 加载环境变量
export $(cat .env.production | xargs)

# 4. 构建镜像
echo "🔨 构建 Docker 镜像..."
docker-compose build --no-cache

# 5. 停止旧容器
echo "🛑 停止旧服务..."
docker-compose down

# 6. 启动新容器
echo "🚀 启动新服务..."
docker-compose up -d

# 7. 等待数据库就绪
echo "⏳ 等待数据库启动..."
sleep 10

# 8. 初始化数据库（首次部署）
if [ ! -f ".db_initialized" ]; then
    echo "📊 初始化数据库..."
    docker-compose exec -T backend python init_db.py
    touch .db_initialized
fi

# 9. 健康检查
echo "🔍 健康检查..."
for i in {1..30}; do
    if curl -sf http://localhost:8080/health > /dev/null; then
        echo "✅ 服务启动成功！"
        docker-compose ps
        echo ""
        echo "🌐 访问地址: https://<你的域名>"
        echo "👤 默认管理员: admin / <查看init_db.py>"
        exit 0
    fi
    echo "等待服务启动... ($i/30)"
    sleep 2
done

echo "❌ 服务启动失败，请检查日志:"
docker-compose logs --tail=50
exit 1
```

### 5.3 备份脚本

**文件**：`backup.sh`

```bash
#!/bin/bash
set -e

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

echo "📦 备份数据库..."
docker-compose exec -T postgres pg_dump -U testdeck testdeck > "$BACKUP_DIR/db_$DATE.sql"

echo "📦 备份上传文件..."
tar -czf "$BACKUP_DIR/uploads_$DATE.tar.gz" uploads/

echo "✅ 备份完成: $BACKUP_DIR"
ls -lh $BACKUP_DIR/*$DATE*
```

**检查点**：
- [ ] Nginx 配置测试通过：`nginx -t`
- [ ] HTTPS 证书有效
- [ ] 部署脚本执行成功
- [ ] 外网可访问：`https://<你的域名>`
- [ ] 登录功能正常
- [ ] 数据持久化验证（重启容器后数据不丢失）

---

## 📋 Phase 6: 数据迁移与测试（2h）

### 6.1 导入现有测试用例

**步骤**：
1. 登录管理后台
2. 上传 `Odyssey_测试用例_v1.2.md`（转换为CSV）
3. 批量上传 `过程测试/` 目录下的所有CSV
4. 验证字段映射正确

### 6.2 端到端测试

**测试场景**：
- [ ] 用户注册和登录
- [ ] 上传测试用例集
- [ ] 筛选功能（分层/批次/模块）
- [ ] 执行测试并标记结果
- [ ] 刷新页面进度恢复
- [ ] 多设备同账号进度同步
- [ ] 截图上传飞书
- [ ] PiP 画中画模式
- [ ] 导出测试报告

### 6.3 性能测试

- [ ] 1000条用例加载速度 < 2秒
- [ ] 并发10用户同时测试
- [ ] 数据库查询优化（添加索引）

---

## 📋 Phase 7: 文档与交付（1h）

### 7.1 部署文档

**文件**：`DEPLOYMENT.md`

包含：
- 服务器要求（配置、端口）
- 部署步骤详解
- 环境变量说明
- 常见问题排查

### 7.2 用户手册

**文件**：`USER_GUIDE.md`

包含：
- 登录和注册
- 上传测试用例
- 执行测试流程
- 筛选和导出功能

### 7.3 API 文档

**文件**：`API.md`

所有接口的请求/响应示例

---

## 🎯 关键依赖与前置条件

### 你需要提供：

1. **服务器访问**
   - [ ] SSH 私钥文件
   - [ ] 服务器 IP 和用户名
   - [ ] sudo 权限（或 docker 权限）

2. **域名配置**
   - [ ] 域名已指向服务器 IP
   - [ ] DNS 生效确认

3. **SSL 证书**（二选一）
   - [ ] 已有证书文件（.crt 和 .key）
   - [ ] 或使用 Let's Encrypt 自动申请

4. **飞书配置**（可选，保留截图功能）
   - [ ] APP_ID 和 APP_SECRET
   - [ ] 多维表格 TOKEN 和 TABLE_ID

### 我需要的权限：

- [ ] 读写项目目录权限
- [ ] Docker 命令执行权限（`docker ps`, `docker-compose`）
- [ ] Nginx 配置文件编辑权限（或你手动添加）
- [ ] 防火墙端口开放（80, 443, 8080）

---

## 📊 风险与应对

| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|----------|
| CSV 格式不统一 | 高 | 中 | 自动字段映射 + 手动校正 |
| 数据库迁移失败 | 中 | 高 | 提前备份 + 回滚脚本 |
| Nginx 配置冲突 | 中 | 中 | 使用独立配置文件 + 测试 |
| JWT token 泄露 | 低 | 高 | HTTPS + 短过期时间 + 刷新token |
| 服务器资源不足 | 低 | 中 | 监控 + 优化查询 + 升级配置 |

---

## ✅ 验收标准

### 功能验收
- [ ] 用户可以通过域名访问系统
- [ ] 登录/注册功能正常
- [ ] 支持上传 CSV 和 JSON 格式测试用例
- [ ] 按分层/批次/模块筛选用例
- [ ] 执行记录实时保存到数据库
- [ ] 多设备登录同步进度
- [ ] PiP 画中画模式正常
- [ ] 截图上传飞书成功

### 性能验收
- [ ] 首页加载 < 3秒
- [ ] 用例列表加载（100条）< 1秒
- [ ] 标记操作响应 < 500ms
- [ ] 支持 10 并发用户

### 安全验收
- [ ] HTTPS 强制跳转
- [ ] JWT token 有效期 24 小时
- [ ] 密码 bcrypt 加密
- [ ] SQL 注入防护
- [ ] XSS 防护

### 运维验收
- [ ] Docker 容器自动重启
- [ ] 数据库自动备份脚本
- [ ] 日志正常记录
- [ ] 健康检查接口可用

---

## 🚀 开始执行

明天你提供服务器访问后，我会按以下顺序执行：

1. **SSH 连接测试**（10分钟）
2. **环境检查**：Docker、Nginx、域名（10分钟）
3. **Phase 1-2**：数据库 + 后端开发（6小时）
4. **Phase 3**：前端改造（4小时）
5. **Phase 4-5**：Docker + Nginx 部署（3小时）
6. **Phase 6-7**：测试与文档（2小时）

**预计总耗时**：16-18 小时（分2-3天完成）

---

## 📞 需要你协助的地方

1. **Nginx 配置**：你直接给我域名后，我生成配置文件，你复制到服务器
2. **SSL 证书**：如果没有，我帮你用 Let's Encrypt 申请
3. **防火墙**：开放 80、443、8080 端口
4. **测试验收**：开发完成后，你用多个设备测试同步功能

准备好了就把服务器信息发我，开始干！💪
