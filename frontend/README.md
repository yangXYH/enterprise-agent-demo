# Vue 开发界面

无需安装的离线演示位于仓库根目录 `index.html`。

本目录为原业务界面的 Vue 3 + TypeScript 源码。开发需要 Node.js 22.12+ 与已配置的 FastAPI 后端：

```bash
npm ci
npm run dev
npm run build
```

后端 `/api` 代理默认指向 `http://127.0.0.1:8000`。开发环境需要自行准备测试数据库和演示账号，不能使用生产数据或凭证。
