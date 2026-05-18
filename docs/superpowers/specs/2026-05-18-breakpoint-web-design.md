# Breakpoint Web 版设计文档

## 概述

为 Breakpoint（自动化网球精彩片段提取系统）构建 Web 版本，包含产品 Landing Page 和在线 Web 应用，支持桌面端和移动端访问。采用单体部署架构，双区域部署（国内阿里云 + 海外 Azure）。

## 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 网站目标 | Landing Page + Web App | 推广 + 在线使用 |
| 处理模式 | 混合模式 | 轻量操作客户端，重计算服务端 |
| 用户规模 | 小规模（1-5 并发） | 个人/朋友使用 |
| 技术栈 | FastAPI + React | 复用现有 engine 和桌面端组件 |
| 设计风格 | 运动/活力 | 明亮配色，网球元素，面向运动爱好者 |
| 认证 | 免费 + 登录 | 注册账号即可使用全部功能 |
| 前端位置 | 独立 `web/` 目录 | 与 `desktop/`、`engine/` 并列 |

## 架构

### 整体架构

```
国内用户 → DNS → 阿里云 ECS
                  ├── Nginx + React SPA
                  ├── FastAPI + Celery + Redis + PostgreSQL
                  └── 阿里云 OSS (视频存储)

海外用户 → DNS → Azure VM
                  ├── Nginx + React SPA
                  ├── FastAPI + Celery + Redis + PostgreSQL
                  └── Azure Blob Storage (视频存储)

共用同一份代码，通过环境变量切换存储后端和认证 provider
```

### 服务组件（docker-compose）

- **Nginx**：反向代理 + 静态文件服务（React SPA）
- **FastAPI**：API 服务 + WebSocket 进度推送
- **Celery Worker**：异步视频处理任务（调用 engine）
- **Redis**：任务队列 + 缓存
- **PostgreSQL**：用户、项目、分析结果持久化

### 存储

- 视频文件和导出文件存放在对象存储（国内 OSS / 海外 Azure Blob）
- 客户端通过预签名 URL 直传对象存储，不经过 API 服务器
- 存储接口抽象为 `StorageBackend` 基类，子类分别实现 OSS 和 Azure Blob

### 认证

- JWT 认证（短有效期 access token + 长有效期 refresh token）
- 认证 provider 可插拔：
  - 国内：手机号 / 微信登录
  - 海外：Google / GitHub OAuth
- 通过环境变量切换 provider

## 项目目录结构

```
Breakpoint/
├── engine/          # 现有 Python 引擎（共用）
├── desktop/         # 现有 Electron 桌面端
├── web/             # 新增 Web 版
│   ├── frontend/    # React SPA（Vite + TypeScript）
│   │   ├── src/
│   │   │   ├── pages/       # Landing, Login, App 等页面
│   │   │   ├── components/  # 从 desktop 迁移/改造的组件
│   │   │   ├── api/         # 后端 API 调用层
│   │   │   └── stores/      # 状态管理（Zustand）
│   │   └── package.json
│   ├── backend/     # FastAPI 服务
│   │   ├── app/
│   │   │   ├── routers/     # API 路由
│   │   │   ├── services/    # 业务逻辑（调用 engine）
│   │   │   ├── models/      # 数据库模型
│   │   │   ├── storage/     # 存储抽象（OSS / Azure Blob）
│   │   │   └── auth/        # 认证 provider
│   │   └── requirements.txt
│   ├── docker-compose.yml
│   ├── nginx.conf
│   └── Dockerfile
└── docs/
```

## 前端页面结构

### 路由

```
/                → Landing Page（产品介绍、功能展示、下载桌面版、注册入口）
/login           → 登录页（国内：手机号/微信，海外：Google/GitHub）
/register        → 注册页
/app             → 主应用（需登录）
/app/projects    → 项目列表（历史分析记录）
/app/new         → 新建项目（上传视频）
/app/:id         → 项目详情（时间线编辑器、片段列表、预览播放）
/app/:id/export  → 导出设置与下载
```

### 用户核心流程

```
Landing → 注册/登录 → 上传视频 → 等待分析（进度条）
→ 时间线编辑器（浏览片段、调整选区、预览）
→ 选择片段 → 导出精彩集锦 → 下载
```

### 移动端适配

- Landing Page：响应式设计，移动端优先
- 时间线编辑器：
  - 桌面端：完整水平时间线 + 拖拽调整
  - 移动端：垂直卡片列表 + 简化预览，支持滑动浏览，放弃精细拖拽
- 视频上传：移动端支持从相册选择或拍摄

### 组件复用

- 从 `desktop/renderer` 迁移视频播放器、片段列表、工具栏组件
- 时间线组件重新适配（去掉 Electron 依赖，加响应式）
- 状态管理从 electron-store 迁移到 Zustand + API

## 后端 API

### 认证

```
POST /api/auth/register     # 注册
POST /api/auth/login        # 登录（返回 JWT）
POST /api/auth/refresh      # 刷新 token
GET  /api/auth/me           # 当前用户信息
```

### 项目管理

```
GET    /api/projects         # 项目列表
POST   /api/projects         # 创建项目（含视频上传预签名 URL）
GET    /api/projects/:id     # 项目详情（含分析结果）
DELETE /api/projects/:id     # 删除项目
```

### 视频处理

```
POST   /api/projects/:id/analyze    # 触发分析（Celery 异步任务）
GET    /api/projects/:id/status     # 查询任务状态
WS     /api/ws/progress/:task_id    # WebSocket 实时进度推送
```

### 片段编辑

```
GET    /api/projects/:id/segments          # 获取片段列表
PUT    /api/projects/:id/segments/:sid     # 修改片段（调整起止时间）
PATCH  /api/projects/:id/segments/select   # 批量选择/取消片段
```

### 导出

```
POST   /api/projects/:id/export          # 触发导出（Celery 异步）
GET    /api/projects/:id/export/download  # 获取导出文件下载链接
```

### 文件上传流程

客户端请求预签名 URL → 直传 OSS/Azure Blob → 回调通知后端 → 触发分析。视频不经过 API 服务器，减轻带宽压力。

## 部署

### 双区域配置

| | 国内（阿里云） | 海外（Azure） |
|--|--------------|-------------|
| 计算 | ECS 2核4G | VM B2s |
| 数据库 | Docker PostgreSQL | Docker PostgreSQL |
| 对象存储 | 阿里云 OSS | Azure Blob Storage |
| 认证 | 手机号 / 微信 | Google / GitHub OAuth |
| 域名 | 需 ICP 备案 | 直接绑定 |
| 预估月费 | ¥150-300 | $15-40 |

### 部署方式

- 同一份代码，通过环境变量区分区域配置
- docker-compose 一键启动全栈
- CI/CD 分别推送到两个区域

### 注意事项

- 两套部署数据隔离，不做跨区同步
- 国内部署配置 npm/pip 阿里云镜像源
- 国内域名需要 ICP 备案（约 1-2 周）
- 阿里云轻量应用服务器价格更低但带宽有限
