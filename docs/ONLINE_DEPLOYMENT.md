# 打包上传后生成在线演示链接

这一部署包包含原 Vue 界面、FastAPI 后端、MySQL 测试库及 Caddy 网站入口。访问者打开链接即可进入完整免登录演示。

## 上传到可运行 Docker 的云服务器

服务器需要 Docker Engine、Docker Compose 2.24+、Python 3，并允许外部访问 TCP 80/443。包中包含源代码和原前端编译产物，不包含本机虚拟环境、上传文件、真实数据库或环境密钥。

1. 下载[项目 ZIP](https://github.com/yangXYH/enterprise-agent-demo/archive/refs/heads/main.zip)，上传服务器并解压，也可以直接克隆 GitHub 仓库。
2. 进入解压目录，生成只保存在服务器上的随机测试数据库密码：

```bash
python3 tools/prepare_online.py
docker compose --env-file .env.online -f compose.online.yml up -d --build
```

首次启动会编译原前端、安装后端依赖并生成全部测试数据，可能需要数分钟。查看启动日志：

```bash
docker compose --env-file .env.online -f compose.online.yml logs -f app
```

应用健康检查成功后，网站入口启动。此时访问 `http://服务器公网IP/`，不需要账号密码。数据库没有对外开放端口；数据库、附件和设计图片使用独立持久化卷。

## 使用自己的 HTTPS 域名

先将域名解析到服务器公网 IP，并开放 80/443，再在首次生成配置时使用：

```bash
python3 tools/prepare_online.py --domain demo.example.com
docker compose --env-file .env.online -f compose.online.yml up -d --build
```

`demo.example.com` 只是格式示例，需要替换为自己的域名。已有 `.env.online` 时，初始化工具会保留现有内容；可以手动将其中 `DEMO_PUBLIC_HOST=:80` 改为实际域名，再运行上述 Compose 命令。Caddy 会按域名配置申请与续期 HTTPS 证书，详见[官方 HTTPS 说明](https://caddyserver.com/docs/automatic-https)。

## 验证与维护

访问网站后确认右上角“免登录演示”、原部门导航及业务数据。`/api/demo/status` 返回完整应用及测试库归属标记。需要接口验收时，在已安装项目 Python 依赖的环境中运行：

```bash
python tools/smoke_full_demo.py --url https://你的实际演示域名
```

停止服务使用：

```bash
docker compose --env-file .env.online -f compose.online.yml down
```

重新启动保留数据库与附件。需要 AI 在线调用时，将自己的兼容模型服务参数填写到服务器 `.env.online` 的 `LLM_*` 项，再重建应用容器。默认不携带真实模型凭证，ERP 自动同步关闭。

## 托管平台

也可以使用支持 Docker 和 MySQL 的托管平台。已有 Docker Compose 可以作为配置依据，但平台通常要求分别配置应用、数据库、持久化卷和域名，不能只上传 ZIP。Railway 的[官方部署说明](https://docs.railway.com/guides/docker-compose)提供了对应步骤。连接部署平台账号后才能创建实际在线资源和访问域名。

源码下载地址不是在线演示地址。本文中公网 IP、域名都需要在实际部署后确定；没有预先编造演示 URL。

验证范围：应用本机运行及业务接口已测试；当前开发电脑未安装 Docker，本配置尚未完成云服务器端到端部署验证。
