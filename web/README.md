# Breakpoint Web：本地部署指南

本目录包含 Breakpoint Website 的完整本地环境：

- Next.js 前端
- FastAPI API
- Celery worker 与 Beat
- PostgreSQL
- Redis
- MinIO 对象存储
- Mailpit 本地邮件收件箱

推荐使用 Docker Compose 启动整套服务。

## 1. 前置条件

安装以下软件：

- Git
- Docker Desktop
- Windows 用户需要启用 WSL 2 和 Virtual Machine Platform

确认 Docker 引擎已启动：

```powershell
docker version
docker compose version
```

如果 Windows 上 Docker Desktop 尚未运行：

```powershell
docker desktop start
```

## 2. 创建本地配置

从仓库根目录进入 `web`：

```powershell
Set-Location web
```

首次启动前，生成一个稳定的本地 JWT 密钥并保存到 `web\.env`：

```powershell
$secret = [Convert]::ToBase64String(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(48)
)
"BREAKPOINT_JWT_SECRET_KEY=$secret" | Set-Content .env
```

macOS 或 Linux：

```bash
cd web
printf 'BREAKPOINT_JWT_SECRET_KEY=%s\n' \
  "$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" > .env
```

不要在每次启动时重新生成该密钥，否则现有登录会话会失效。不要提交
`web\.env`。

## 3. 构建并启动

在 `web` 目录运行：

```powershell
docker compose up -d --build
```

首次构建需要下载基础镜像并安装媒体处理依赖，耗时会比后续启动更长。
数据库迁移会在 API 容器启动时自动执行。

查看服务状态：

```powershell
docker compose ps
```

API 状态应为 `healthy`，其余长期运行服务应为 `Up`。`minio-init`
成功创建 bucket 后显示 `Exited (0)` 是正常现象。

## 4. 访问地址

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| Website | http://localhost:3000 | Breakpoint 前端 |
| API | http://localhost:8000 | FastAPI |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| Mailpit | http://localhost:8025 | 验证邮件和密码重置邮件 |
| MinIO API | http://localhost:9000 | 浏览器直传使用 |
| MinIO Console | http://localhost:9001 | 对象存储管理界面 |

MinIO 本地账号：

```text
Username: minioadmin
Password: minioadmin
```

这些默认凭据仅用于本地开发。

## 5. 注册与验证邮件

本地环境不会把邮件发送到真实邮箱服务。注册时可填写任意合法且未注册过的
邮箱，例如：

```text
player-local@example.com
```

然后打开 Mailpit：

http://localhost:8025

在收件箱中打开 `Verify your Breakpoint account`，点击验证链接并设置密码。

同一未验证邮箱在现有验证 token 仍有效时重复注册，不会重复发送邮件。这是
防止邮件轰炸的预期行为。需要重新测试完整注册流程时，请换一个新的邮箱地址。

## 6. 验证服务

```powershell
Invoke-WebRequest http://localhost:3000 -UseBasicParsing
Invoke-WebRequest http://localhost:8000/health/live -UseBasicParsing
Invoke-WebRequest http://localhost:8000/health/ready -UseBasicParsing
Invoke-WebRequest http://localhost:8025 -UseBasicParsing
Invoke-WebRequest http://localhost:9000/minio/health/live -UseBasicParsing
```

以上请求都应返回 HTTP 200。

## 7. 日常启动与停止

保留数据库和上传文件并停止容器：

```powershell
docker compose stop
```

再次启动：

```powershell
docker compose start
```

停止并删除容器，但保留数据卷：

```powershell
docker compose down
```

代码或 Dockerfile 修改后重建：

```powershell
docker compose up -d --build
```

## 8. 查看日志

查看全部日志：

```powershell
docker compose logs -f
```

查看指定服务：

```powershell
docker compose logs -f api
docker compose logs -f frontend
docker compose logs -f worker beat
```

最近 100 行：

```powershell
docker compose logs --tail=100 api
```

## 9. 完全重置本地数据

以下命令会永久删除本地数据库、账号、项目、上传视频及 MinIO 数据：

```powershell
docker compose down -v
docker compose up -d --build
```

仅在确实需要全新环境时使用。

## 10. 常见问题

### Docker 命令无法连接

确认 Docker Desktop 正在运行：

```powershell
docker desktop start
docker info
```

如果提示 WSL 2 或 Virtual Machine Platform 未启用，需要以管理员权限安装
WSL 2，并在系统要求时重启：

```powershell
wsl --install --no-distribution
```

### Mailpit 没有收到邮件

1. 确认访问的是 http://localhost:8025。
2. 使用一个新的合法邮箱地址。
3. 检查 API 与 Mailpit 日志：

```powershell
docker compose logs --tail=100 api mailpit
```

### `Upload & analyze` 按钮不可用

先点击 `Choose video` 并等待页面读取视频元数据。页面显示文件名、时长和
大小后按钮才会启用。上传进行中或取消清理尚未完成时，按钮也会暂时禁用。

### 端口被占用

默认使用以下端口：

```text
3000, 8000, 8025, 9000, 9001, 1025, 5432, 6379
```

停止占用端口的程序，或修改 `docker-compose.yml` 中对应的宿主机端口映射。

