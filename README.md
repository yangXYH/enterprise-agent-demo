# Enterprise Agent · 企业 AI 工作台

面向面试展示的企业 AI 应用项目。保留 Vue 3 + TypeScript + FastAPI 的业务实现，并提供无需安装、无需登录的离线测试数据演示。

![经营总览预览](demo/preview.png)

## 克隆后直接查看

```bash
git clone https://github.com/yangXYH/enterprise-agent-demo.git
cd enterprise-agent-demo
```

**双击根目录 `index.html` 即可打开。** Windows 也可双击 `start-demo.cmd`。请保留完整目录结构。

此入口不需要 Node.js、Python、数据库、API Key 或网络连接。请使用现代 Chrome、Edge、Firefox 或 Safari。

如果希望通过 localhost 查看，安装 Node.js 后运行：

```bash
node tools/serve_demo.mjs
```

打开 <http://127.0.0.1:4173>。该预览服务只监听本机，并只提供演示页面与静态资源。

## 可以演示什么

| 模块 | 可操作内容 |
| --- | --- |
| 经营总览 | 切换月份，查看收入、项目净利、趋势与渠道占比 |
| 店铺报表 | 切换期间和渠道，搜索店铺，核对成本、费用与净利 |
| 库存预警 | 搜索 SKU，筛选低库存，核对安全库存和在途数量 |
| 人事管理 | 搜索测试员工，按部门筛选，查看虚构花名册 |
| 客服看板 | 查看测试客服接待量、解决率、响应时间和满意度 |
| AI 项目看板 | 添加测试项目，推进进度，重置本地演示记录 |
| 数据问答 | 询问测试营收、店铺排行、库存缺口与人员统计 |

各数据页面支持 CSV 导出，支持明暗主题与移动端布局。项目修改仅保存在当前浏览器；导出的文件只包含当前筛选下的测试记录。

**离线问答使用本地规则计算，不调用大模型。** 完整后端源码保留模型接入、经营查询、会话持久化和知识检索等实现；离线入口用于展示交互与数据口径，不能替代真实 AI 服务的效果评估。

## 测试数据

所有企业、姓名、店铺、商品、金额和联系方式均为虚构测试内容。数据由固定公式生成，与任何真实员工、交易或公司经营结果无关。

- 4 家测试店铺、9 个月、36 条经营明细。
- 24 位测试员工、4 个部门；联系方式为不可拨打的测试标识。
- 18 个测试 SKU、5 位测试客服、4 个初始演示项目。
- 项目净利 = 营业收入 − 商品成本 − 已录费用；未计人工与税费。

重新生成数据（仅依赖 Python 标准库）：

```bash
python tools/generate_demo_data.py
python -m unittest discover -s tests -p demo_data_test.py
python tools/check_public_demo.py
```

## 源码结构

```text
index.html                 克隆后直接打开的演示入口
demo/                      离线页面、图表、测试数据与预览图
frontend/src/              Vue 3 + TypeScript 原业务界面
main.py / *_routes.py      FastAPI 接口与业务路由
utils/                     权限、经营分析、问答、库存、人事等服务
database/                  数据库结构与迁移
tools/                     测试数据生成、导入导出和检查工具
tests/                     业务测试与演示数据校验
```

## 运行完整开发版本

完整 Vue + FastAPI 版本需要独立 MySQL 数据库、Python 3.12+、Node.js 22.12+，以及按实际功能选择的外部服务配置。此模式需要开发环境，不属于双击即可查看的离线入口。

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

复制 `.env.test.example` 为 `.env.test`，填入独立测试数据库的账号与密码；按 `database/rebuild_from_local_schema.sql` 准备空测试库。该脚本会重建其命名的数据库，请只对可丢弃的本地测试库执行。环境变量或数据库名称需要与初始化脚本保持一致。

```bash
# Windows PowerShell:
$env:APP_ENV="test"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

在另一个终端启动 Vue 界面：

```bash
cd frontend
npm ci
npm run dev
```

Vue 开发界面位于 <http://localhost:5717>，API 位于 <http://127.0.0.1:8000>。完整后端需要自行准备演示账号和模块测试数据；本仓库没有生产账号或生产数据。模型、ERP 等集成默认不提供真实凭证。

## 开源处理

本演示仓库使用独立的新 Git 历史。原始员工文件、经营资料、真实数据库、本地环境配置、公司图片、运行产物及包含业务金额的专用导入脚本不在公开版本内。

参见 [数据说明](docs/DEMO_CLEANUP.md)、[验证记录](docs/VALIDATION.md) 与 [数据库配置](DATABASE_ENVIRONMENT.md)。项目采用 MIT 许可证。
