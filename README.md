# 📈 StockPilot · 个人 AI 投资助手（桌面版）

> 本地优先（local-first）的 A股 + 基金投资助手：行情、K线/净值、技术指标、**多角色 AI 决策**、智能选股、策略回测、模拟盘。
> **所有数据保存在你本机，不上传任何云端。** 可打包成单目录桌面程序，双击即跑，无需安装 Python/Node。

---

## ✨ 功能特性

- 🔍 **搜索与自选**：搜索股票 / 基金 / ETF，一键加入自选，实时涨跌（红涨绿跌，符合 A股习惯）。
- 📊 **K线与指标**：股票/ETF K线、基金净值曲线，叠加 MACD / RSI / KDJ / BOLL 信号与 MA 均线、成交量。
- 🤖 **多角色 AI 决策卡片**：技术派 / 价值派 / 风控派 / 激进派，各自独立结论 + 角色共识（由 DeepSeek 驱动，可选）。
- 📋 **每日投资日报**：汇总大盘与自选的多角色观点、风险与纪律提醒，支持下载 HTML / 复制 Markdown。
- 🔍 **智能选股**：3 套策略（低估价值 / 强势动量 / 技术金叉）× 3 档股票池（全A / 沪深300 / 自选），秒出候选清单与命中理由。
- 📈 **策略回测**：双均线 / MACD 历史回测，输出资金曲线（策略 vs 买入持有）+ 交易明细 + 绩效指标，含真实 A股成本模型（佣金/印花税/过户费/滑点）。
- 💰 **模拟盘**：虚拟买卖，按实时行情计算持仓市值与浮动盈亏，用于验证策略。
- 📰 个股相关新闻、板块行情与轮动、投资者适当性管理等。
- ⚙️ **设置**：应用内配置 DeepSeek Key、AI 模型、速率限制等。

> ⚠️ 所有 AI 建议、回测与模拟结果**仅供参考，不构成投资建议**，投资有风险。

---

## 🛠 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript |
| 后端 | FastAPI（Python）+ SQLite（aiosqlite）+ JWT |
| 桌面壳 | pywebview（原生窗口，单端口 `127.0.0.1:8000`） |
| 打包 | PyInstaller（`--onedir`，输出 `StockPilot.exe`） |
| AI | DeepSeek API（`deepseek-v4-flash` / `deepseek-v4-pro`） |

---

## 📦 下载与安装（推荐）

前往仓库 **Releases** 页面下载安装包：

👉 **https://github.com/yygg693/StockPilot/releases**

- 下载 `StockPilot-win64-v2.0.0.zip`（约 22 MB）。
- 解压到任意目录，**双击 `StockPilot.exe`** 即启动（首次启动会本机自动建库）。
- 需要系统已安装 **WebView2 运行时**（Windows 10/11 通常已自带；若缺失会提示安装）。

> 数据全部落在 `%APPDATA%\StockPilot\data`，不会写进安装目录，卸载直接删文件夹即可。

---

## 🚀 快速开始

### 方式一：直接用桌面程序（最简单）
见上方「下载与安装」。启动后自动打开 GUI 窗口，无需命令行。

### 方式二：从源码运行（开发 / 调试）
```bash
# 1. 安装后端依赖
pip install -r requirements.txt

# 2. 启动（前端用 dev server，或先 build）
python -m uvicorn backend.app.main:app --port 8000 --reload
# 另开一个终端启动前端：
cd frontend-v2 && npm install && npm run dev
# 浏览器打开 http://127.0.0.1:5173
```

### 方式三：从源码构建桌面 exe
```bash
# 需要 Python 3.11+ 与 Node 18+，已安装 pyinstaller / pywebview
# config.yaml 不存在时会自动从 config.example.yaml 生成
build.bat          # Windows
# 产物在 dist/StockPilot/StockPilot.exe
```

---

## 🤖 AI 功能配置（DeepSeek）

AI 功能默认关闭规则分析降级；接入 DeepSeek 后获得多角色决策卡片与日报。
**三种配置方式（任选其一）**，密钥均**不写入源码、不进仓库、不进安装包**：

1. **环境变量（推荐，最安全，不落盘）**
   - Windows：`set STOCKPILOT_AI_API_KEY=sk-xxxxx`
   - Linux/Mac：`export STOCKPILOT_AI_API_KEY=sk-xxxxx`
2. **应用内设置页**：左侧「⚙️ 设置」填入 DeepSeek Key，保存即生效；密钥在本机以**设备绑定加密**形式存于 `%APPDATA%\StockPilot\data/ai_config.json`，换机器不可用。
3. **config.yaml**：复制 `config.example.yaml` 为 `config.yaml` 后填入（不推荐，注意 `.gitignore` 已忽略 `config.yaml`）。

注册地址：https://platform.deepseek.com （模型默认 `deepseek-v4-flash`，可选 `deepseek-v4-pro`）。
未配置 Key 时系统自动降级为「规则引擎分析」，其余功能完全可用。

---

## 🔒 隐私与数据安全

本项目**本地优先**，对你负责：

- ✅ 行情/净值来自公开行情接口（腾讯/AKShare），**仅用于本机查询**，不发往任何第三方私有服务。
- ✅ 你的自选股、模拟交易、本地账户等数据**全部保存在本机 SQLite**（`%APPDATA%\StockPilot\data/stockpilot_v2.db`）。
- ✅ AI Key 仅在本地使用；一旦通过环境变量或设置页配置，仅存于本机，不会随仓库或安装包分发。
- ✅ 仓库与安装包**不含**任何真实密钥、数据库、日志：`.gitignore` 忽略了 `.env` / `config.yaml` / `data/*.db` / `data/ai_config.json` / `*.log`；打包脚本（`StockPilot.spec`）额外排除日志与数据库，确保分发物干净。
- 🧹 想彻底清除本机数据：删除 `%APPDATA%\StockPilot\data` 文件夹，下次启动自动重建空库。

---

## 📁 目录结构

```
StockPilot/
├── backend/
│   └── app/
│       ├── main.py          # FastAPI 入口（应用工厂）+ 路由注册
│       ├── core/            # 配置 / 安全 / 异常 / 日志 / HTTP 客户端 / 限流
│       ├── routers/         # 路由模块（auth/quote/screener/backtest/trade/ai/fund/sector/report/portfolio/suitability/system）
│       ├── services/        # 数据源 / AI / 回测 / 缓存
│       ├── trading/         # 交易引擎 / 策略 / 风控
│       ├── db/              # SQLite 连接（aiosqlite）
│       └── deps.py          # 依赖注入
├── frontend-v2/             # Vue3 + Vite + TS 前端（桌面应用 UI）
├── desktop.py               # 桌面壳（pywebview 原生窗口）
├── scripts/                 # 开发脚本（precheck / watchdog / 备份 / 接口自检）
├── data/                    # 运行期数据（SQLite 库、全A 快照；git 忽略隐私文件）
├── config.example.yaml      # 配置示例（已提交；config.yaml 为本地私密，被忽略）
├── StockPilot.spec          # PyInstaller 打包规格（含隐私安全排除项）
├── build.bat                # 一键构建桌面 exe（Windows）
├── requirements.txt / pyproject.toml
└── tests/                   # pytest 测试
```

> 注：微信小程序版本为独立项目（微信云开发，不经本仓库 FastAPI），源码不在此仓库内。

---

## 🧑‍💻 开发指南

- 后端测试：`pytest`（见 `tests/`）。
- 接口文档：启动后访问 `http://127.0.0.1:8000/docs`（Swagger）。
- 限流：桌面单用户场景已放宽 AI 限流（默认 60 次/分钟/IP，且本地回环豁免）。
- 数据源：腾讯行情接口（稳定主力）+ AKShare（代码清单 / 基金净值 / 新闻）。选股「全A」池基于本地快照 `data/universe_snapshot.json`，首次可在「选股」页点「重建全A快照」。

---

## ⚠️ 免责声明

本软件为**个人学习与研究工具**，所有行情、AI 分析与回测/模拟结果均**不构成任何投资建议**。使用本软件产生的任何投资决策与损失，由使用者自行承担。投资有风险，入市需谨慎。

---

## 📄 许可证

MIT License —— 可自由使用、修改与分发，请保留版权声明。
