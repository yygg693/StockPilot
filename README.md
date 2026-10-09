# 📈 StockPilot · 个人 AI 投资助手

个人专属的 A股 + 基金投资助手：行情、K线/净值、技术指标、AI 决策卡片，本地部署，数据不外传。

> 当前为 **Phase 3**：选股 / 回测 / 模拟盘（已含 Phase 1 行情指标 + Phase 2 多角色 AI + 自动日报）
> 后续：P4 自动交易

## 快速开始

### 1. 安装依赖（首次）
```bash
cd D:\StockPilot
pip install -r requirements.txt
```

### 2. 配置 DeepSeek（可选，不配也能用规则分析）
推荐通过**环境变量**配置（不落盘，最安全）：
- Windows：`set STOCKPILOT_AI_API_KEY=sk-xxxxx`（或「系统设置 → 环境变量」永久配置）
- Linux/Mac：`export STOCKPILOT_AI_API_KEY=sk-xxxxx`

也可在网页左侧「⚙️ 设置」填入 DeepSeek Key（https://platform.deepseek.com 注册），保存即生效，无需重启；密钥只保存在后端内存中，不写入磁盘。
> 没填 key 时系统自动降级为「规则引擎分析」，功能不受影响。

### 3. 启动
双击 `启动.bat`，或命令行：
```bash
python -m uvicorn backend.app.main:app --port 8000
```
浏览器打开 http://127.0.0.1:8000

## 功能一览
- 🔍 搜索股票 / 基金 / ETF，一键加自选
- ⭐ 自选管理，实时行情涨跌（红涨绿跌）
- 📊 K线（股票/ETF）/ 净值曲线（基金）+ MACD/RSI/KDJ/BOLL 指标信号（图表叠加 MA 均线与成交量）
- 🤖 **多角色 AI 决策卡片**：技术派 / 价值派 / 风控派 / 激进派，各自独立结论 + 角色共识
- 📋 **每日投资日报**：汇总大盘与自选的多角色观点、风险与纪律提醒，可下载 HTML / 复制 Markdown
- 🔍 **智能选股**：3 套策略（低估价值 / 强势动量 / 技术金叉）× 3 档股票池（全A / 沪深300 / 自选），秒出候选清单与命中理由。金叉策略对全A 预筛「盈利+有成交额」活跃股后取流动性前 N 名（默认 200，可调）拉 K线，覆盖面远大于旧版
- 📈 **策略回测**：双均线 / MACD 策略历史回测，输出资金曲线（策略 vs 买入持有）+ 交易明细 + 绩效指标。**真实 A股 成本模型**（佣金万2.5/最低5元 + 印花税万5仅卖 + 过户费 + 千1滑点）、全仓 100 股整数倍、可选止损比例；指标区分净收益(扣费) / 毛收益(未扣费) / 持有收益 / 最大回撤 / 胜率 / 止损触发次数 / 总成本
- 💰 **模拟盘**：虚拟买卖，按实时行情计算持仓市值与浮动盈亏，验证策略用
- 📰 个股相关新闻
- ⚙️ **设置**：网页内配置 DeepSeek Key

## 目录结构
```
StockPilot/
├── backend/
│   └── app/
│       ├── main.py          # FastAPI 入口（create_app 工厂）+ 路由注册
│       ├── core/            # 配置 / 安全 / 异常 / 日志 / HTTP 客户端 / 限流
│       ├── routers/         # 12 个路由模块（行情/交易/AI/回测/选股/认证...）
│       ├── services/        # 数据源 / AI / 回测 / 缓存
│       ├── trading/         # 交易引擎 / 策略 / 风控
│       ├── db/              # SQLite 连接（aiosqlite）
│       └── deps.py          # 依赖注入
├── frontend-v2/             # Vue3 + Vite + TS Web 端（桌面应用前端）
├── desktop.py               # 桌面壳（pywebview 原生窗口：dev/prod/build 模式）
├── data/                    # SQLite 库、全A快照、缓存
├── config.yaml              # 主配置（环境变量 > config.yaml > 默认）
├── tests/                   # pytest 测试（135 用例）
├── requirements.txt / pyproject.toml
└── 启动.bat                 # 一键启动（自动建 venv + 装依赖 + 健康检查）
```
> 微信小程序源码在独立目录 `C:\Users\22091\WeChatProjects\paper-stock-board`（微信云开发，不经 FastAPI）；仓库内 `miniapp-legacy` 为已废弃副本，勿修改。

## 选股 / 回测 / 模拟盘 用法
- **选股**：左侧「🔍 选股」→ 选策略 + 股票池 →「开始选股」。全A 池扫本地快照(~5200只)；金叉策略可设「金叉扫描数」(默认200)控制拉 K线范围。首次用全A 先点「🔄 重建全A快照」。
- **回测**：左侧「📈 回测」→ 填代码 + 策略(双均线/MACD) + 快慢线 + 回看根数 → 可设止损%/佣金/印花税/滑点/初始资金 →「运行回测」。默认 A股 真实成本：净收益已扣费，毛收益未扣费，二者差额即摩擦成本。
- **模拟盘**：左侧「💰 模拟盘」→ 填代码 + 数量 →「买入/卖出」，自动按现价计算盈亏。数据为虚拟，仅供学习。

## 每日日报（自动）
点击左侧「📋 每日日报」即可一键汇总大盘与全部自选的多角色观点、风险与纪律提醒；支持下载 HTML、复制 Markdown。

命令行 / 定时（无需打开网页）：
```bash
cd D:\StockPilot
python -m backend.cli daily --save     # 生成并打印，同时将 HTML/Markdown 存入 data/
```
Windows 定时任务（每天收盘后 15:30 自动生成）：
- 任务计划程序 → 创建任务 → 触发器「每天 15:30」
- 操作：启动程序 `python`，参数 `-m backend.cli daily --save`，起始于 `D:\StockPilot`
- 或 cron（Linux/Mac）：`30 15 * * 1-5 cd /path/StockPilot && python -m backend.cli daily --save`

## 说明
- 数据源：腾讯行情接口（qt.gtimg.cn，稳定主力，须带 Referer 头）+ AKShare（`stock_info_a_code_name()` 取全A 代码清单、基金净值/新闻）。行情/K线优先腾讯，基金净值/新闻走 AKShare。
- 选股「全A」池基于**本地全市场快照** `data/universe_snapshot.json`：后台用「AKShare 代码清单(~5530) + 腾讯批量行情(每批120只)」合成 PE/PB/涨跌幅/成交额，磁盘缓存 6h。首次或想刷新时，在「🔍 选股」页点「🔄 重建全A快照」（非阻塞，前端轮询进度）。快照缺失时自动降级为代码清单/白马清单，功能不中断。
- 原东财 `stock_zh_a_spot_em()` 在本机网络环境被墙不可用，已不再依赖。
- ⚠️ 所有 AI 建议与回测/模拟结果仅供参考，不构成投资建议，投资有风险。
