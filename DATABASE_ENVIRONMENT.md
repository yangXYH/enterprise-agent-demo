# 数据库环境隔离

应用通过 `APP_ENV` 区分测试和正式数据库：

- 测试启动脚本设置 `APP_ENV=test`，读取 `.env.test`。
- 正式启动脚本设置 `APP_ENV=production`，读取 `.env.production`。
- 进程环境变量优先于配置文件；正式环境缺少数据库配置时会直接启动失败，不会回退到 `root/root`。

## 测试环境

```powershell
Copy-Item .env.test.example .env.test
```

根据测试数据库实际地址、库名和账号修改 `.env.test`。测试库不要填写正式服务器的地址、库名或账号。使用 `start_project.ps1` 启动测试服务。

## 正式环境

在服务器项目目录执行：

```powershell
Copy-Item .env.production.example .env.production
```

`.env.production` 应包含服务器数据库配置：

```text
APP_ENV=production
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=enterprise_agent_db
DB_USER=enterprise_agent
DB_PASSWORD=<服务器数据库密码>
```

正式启动入口会设置 `APP_ENV=production`，因此不会读取测试数据库配置。`.env.production` 已被 Git 忽略，不能提交到仓库。
