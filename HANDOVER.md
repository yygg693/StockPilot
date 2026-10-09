# StockPilot 项目交接文档

> 个人 AI 投资助手 · 交接说明
> 最后更新：2026-07-25
> 适用环境：Windows（Git Bash / PowerShell）+ Python 3.13 + Node 22

本文件用于把 `D:\StockPilot` 项目的背景、结构、运行方式、关键模块、已知坑与后续路线一次性交接清楚。新人接手后照着「快速上手」即可把服务跑起来。

---

## 0. 一句话定位

StockPilot 是一个**本地运行的个人股票投资助手**：后端 FastAPI 聚合腾讯行情 + AKShare 数据，前端用 Tabler + 本地 echarts 做交互面板，并接入 DeepSeek 做多角色 AI 决策。当前已具备：实时行情/盘口、K线+技术指标、估值分位、财务摘要、新闻、选股、回测、模拟盘、行业扫描、智能选基金，以及一套「鸣潮·爱弥斯」全息暗色皮肤。

---

## 1. 快速上手

### 1.1 环境
- Python 3.13（沙箱推荐用托管版 `C:\Users\22091\.workbuddy\binaries\python\versions\3.13.12\python.exe`；系统版 `D:\Python313\python.exe` 也可）
- 依赖见 `requirements.txt`：fastapi / uvicorn / akshare / pandas / numpy / requests / pyyaml / openai

### 1.2 启动（两种方式任选）
- **双击启动**：`D:\StockPilot\启动.bat`（已写好，内部 `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`）
- **命令行**：
  ```bash
  cd /d/StockPilot
  python -m uvicorn backend.main:app --port 8000
  ```
启动后浏览器打开 **http://127.0.0.1:8000** 即可。

### 1.3 重启 / 释放端口（重要）
- uvicorn **没有 --reload**，改了 Python 代码必须重启才会生效；但 `index.html` 是每次请求从磁盘读，**前端改动刷新页面即可生效**。
- 重启前先释放 8000 端口（Git Bash 用单斜杠）：
  ```bash
  netstat -ano | grep :8000        # 找到占用 PID
  taskkill /F /PID <pid>           # 杀掉旧进程
  ```
- 健康检查：`GET http://127.0.0.1:8000/api/health` → 返回 `{"status":"ok"}` 即正常。

---

## 2. 目录结构

```
D:\StockPilot
├── 启动.bat                 # 一键启动脚本
├── config.yaml              # 全局配置（AI key / 服务 / 缓存 / 纪律参数）
├── requirements.txt
├── README.md                # 早期说明（与本文档互补）
├── UI_SKIN_PLAN.md          # 爱弥斯皮肤设计计划（确认稿）
├── backend/
│   ├── main.py              # FastAPI 入口 + 全部 /api 路由
│   ├── config.py            # 读/写 config.yaml（含 ai 段保存）
│   ├── universe.py          # 全A 股票池快照（AKShare 代码 + 腾讯批量行情）
│   ├── screener.py          # 选股（价值/动量/金叉）
│   ├── backtest.py          # 回测（真实 A股 成本模型）
│   ├── trade.py             # 模拟盘（持仓/买卖，按实时行情算浮动盈亏）
│   ├── fund_screener.py     # 智能选基金（ETF/场外）
│   ├── report.py            # 自动日报
│   ├── cli.py               # 命令行入口（备用）
│   ├── ai/analyst.py        # 多角色 AI 决策（DeepSeek，4 角色并行）
│   ├── data/
│   │   ├── tencent.py       # 腾讯行情源（行情/分时/K线/指数/搜索）
│   │   └── market.py        # 统一数据层（接 tencent + akshare；财务/行业/估值）
│   ├── indicators/mytt.py   # 技术指标（MACD/RSI/KDJ/BOLL/MA 等）
│   └── db/store.py          # SQLite 自选股 + 持仓（stockpilot.db）
├── frontend/
│   ├── index.html           # 全部前端（外壳 + 业务逻辑 + 元素 ID 集中于此）
│   ├── echarts.min.js       # 本地 echarts 5.5.0（勿改回 CDN）
│   ├── vendor/tabler/       # 本地 Tabler v1 核心 css/js + 图标 sprite
│   └── skins/aomi/          # 爱弥斯皮肤资源槽（放 aomi_bg.png 即生效）
└── data/
    ├── stockpilot.db        # 自选/持仓库
    ├── universe_codes.json  # 全A 代码清单缓存（~5530，24h）
    └── universe_snapshot.json # 全A 行情快照（PE/PB/涨跌幅/成交额，6h）
```

---

## 3. 后端模块与职责

| 模块 | 职责 | 关键接口/函数 |
|---|---|---|
| `main.py` | 路由总入口 | 见第 4 节完整 API 表 |
| `data/tencent.py` | 腾讯行情（**必须带 Referer 头** `https://stockapp.finance.qq.com/`，否则返回空） | `get_quote` / `get_kline` / `get_minute` / `get_index_overview` / `search` |
| `data/market.py` | 统一数据层，组合腾讯 + AKShare；财务/行业/估值在此 | `get_quote` / `get_kline` / `get_minute` / `get_news` / `get_financial` / `get_industry_overview` / `get_industry_index` / `get_valuation_history` |
| `universe.py` | 维护全A 股票池快照，支撑估值/动量筛选 | `universe_get_spot` / `build_snapshot`（后台异步） |
| `screener.py` | 选股三策略 | `value` / `momentum` / `golden`（金叉默认扫 top 200） |
| `backtest.py` | 真实 A股 回测（佣金万2.5 最低5元 + 印花税万5 + 过户费万0.1 + 滑点千1） | `ma_cross` / `macd` 策略，输出 equity/trades/metrics |
| `trade.py` | 模拟盘 | `buy` / `sell` / `positions`（按实时行情算浮盈亏） |
| `fund_screener.py` | 智能选基金 | `etf_momentum` / `etf_active` / `open_year` / `open_3y` / `open_steady` |
| `ai/analyst.py` | 多角色 AI 决策（价值/技术/情绪/风控，`ThreadPoolExecutor` 并行 4 角色） | `analyze_multi` |
| `indicators/mytt.py` | 技术指标实现 | MACD/RSI/KDJ/BOLL/MA |
| `db/store.py` | SQLite 自选 + 持仓 | `add_watch` / `remove_watch` / `get_positions` |

---

## 4. API 速查表（main.py）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/index` | 大盘指数概览 |
| GET | `/api/breadth` | 涨跌家数（市场宽度） |
| GET | `/api/search?q=` | 股票搜索（腾讯 smartbox） |
| GET | `/api/watchlist` | 自选股（含行情） |
| POST | `/api/watchlist/add` | 加自选 `{code}` |
| POST | `/api/watchlist/remove` | 删自选 `{code}` |
| GET | `/api/quote?code=` | 实时行情 + 五档盘口 + 估值分位 |
| GET | `/api/financial?code=` | 财务摘要（AKShare，~14s，6h 缓存） |
| GET | `/api/industry/overview` | 行业概览（同花顺源，90 行业） |
| GET | `/api/industry/index?name=` | 行业指数 K线 |
| GET | `/api/valuation-history?code=&years=` | 全市场 PB 10年分位 + 个股截面分位 |
| GET | `/api/kline?code=&period=&limit=` | 日/周/月 K线 |
| GET | `/api/minute?code=` | 分时（实时每笔走向） |
| GET | `/api/news?code=` | 相关新闻（全文） |
| GET | `/api/analyze?code=` | 单角色 AI 分析 |
| GET | `/api/analyze/multi?code=` | 多角色 AI 决策卡片 |
| GET | `/api/daily-report` | 自动日报 |
| GET | `/api/screener?strategy=&universe=&top_n=` | 选股 |
| GET | `/api/universe/status` | 快照数量 + 构建进度 |
| POST | `/api/universe/refresh` | 后台异步重建全A 快照（非阻塞） |
| GET | `/api/fund-screener?strategy=&top_n=` | 智能选基金 |
| GET | `/api/backtest?code=&strategy=&...` | 回测 |
| GET | `/api/trade/positions` | 模拟盘持仓 |
| POST | `/api/trade/buy` | 模拟买入 `{code, qty}` |
| POST | `/api/trade/sell` | 模拟卖出 `{code, qty}` |
| GET/POST | `/api/config` | 读/写配置（含 ai 段） |

---

## 5. 前端架构要点

- **单文件 `frontend/index.html`**：外壳（Tabler 左侧深色导航 + 顶栏）+ 全部业务逻辑/API 调用/元素 ID 都在这一个文件里。JS 未分模块，改动时搜索元素 ID 即可定位。
- **零 CDN 依赖**：echarts=`frontend/echarts.min.js`、Tabler=`frontend/vendor/tabler/`、图标 sprite 均本地托管（uvicorn 经 `/static/` 提供）。**新增依赖勿改回 CDN 硬依赖。**
- **A股 红涨绿跌配色**：`.up`=红、`.down`=绿，全局不可变。echarts 配色由 `spPalette()` 读 CSS 变量实现（当前皮肤红 `#ff5470`、绿 `#2ee6b0`）。
- **图表**：K线升级为 MA5/10/20/60 + 成交量副图 + MACD 副图（JS 自算 EMA12/26/9），红涨绿跌。
- **实时性**：个股详情页 `openDetail` 设 `setInterval(refreshQuote, 3000)` 每 3 秒拉 `/api/quote` 刷新价格/五档/委比；离开详情清定时器。分时页 `/api/minute` 看每笔走向。

### 5.1 鸣潮·爱弥斯皮肤（2026-07-25 上线）
- **全站一次性换肤，已移除原 light/dark 主题切换**。`initTheme()` 仅设置 `data-skin="aomi"` + `data-bs-theme="dark"`。
- 配色 token 集中在 `index.html` 的 `:root`（粉 `#ff5ea8` / 蓝紫 `#a274ff` / 青 `#4fd6ff` 于近黑紫 `#0b0a14→#140b20`），玻璃拟态卡片（`backdrop-filter:blur`）+ 全息网格 + 浮动光晕动画。
- **立绘背景槽位**：把图片命名为 `aomi_bg.png` 放进 `frontend/skins/aomi/` 并刷新即生效（右侧渐隐遮罩，叠加在全息底图上）。不放图也不会报错，仅显示全息底图。
- **版权提示**：官方立绘请使用本人拥有/已授权的素材，仓库不内置任何版权图。
- **详情页布局修正**：原 AI 卡过长导致左侧留空——已改为 左列(图表+AI卡) / 右列(盘口+估值+财务) / 底部(新闻) 的三段式。

---

## 6. 数据源与已知坑（必读）

1. **腾讯行情必须带 Referer 头** `https://stockapp.finance.qq.com/`，否则 `qt.gtimg.cn` 返回空。已在 `tencent.py` 固定。
2. **腾讯单股返回 88 字段**：现价 p[3] / 昨收 p[4] / 今开 p[5] / 成交量(手) p[6] / 外盘 p[7] / 内盘 p[8] / 买1-5 p[9-18] / 卖1-5 p[19-28] / 涨跌 p[31] / 涨跌% p[32] / 高 p[33] / 低 p[34] / 成交额(万元) p[37] / 换手% p[38] / 市盈 p[39] / 市净 p[46] / 涨跌停 p[47-48] / 振幅 p[49] / 量比 p[56]。
3. **成交额单位陷阱**：腾讯 p[37] 单位是「万元」，易算错；全A 快照里统一用 `现价 × 成交量(手) × 100` 折算成「元」再存。
4. **AKShare 沙箱可用性**：
   - ✅ 可用：`stock_info_a_code_name()`（全A ~5530 代码）、`stock_financial_abstract`（财务摘要，~14s）、`stock_news_em`（新闻）、`stock_board_industry_summary_ths`（行业概览，同花顺源）、`stock_board_industry_index_ths`（行业指数K线）、`fund_etf_spot_em`（ETF 实时）、`fund_open_fund_rank_em`（场外基金排行）。
   - ❌ 被墙不可用：东财 `stock_board_industry/concept_em`（行业板块）、`stock_individual_fund_flow`（资金流）、`stock_individual_info_em`（个股档案）。资金流维度暂用「腾讯外盘/内盘 + 委比 + 主力净流入估算」替代。
5. **回测成本模型**：佣金万2.5（最低5元，双边）+ 印花税万5（仅卖）+ 过户费万0.1 + 滑点千1；全仓、100股整数倍；默认本金 50 万，茅台等高价股 100 万以下买不起 1 手→0 交易，属正常。

---

## 7. 配置（config.yaml）

- `ai.api_key`：DeepSeek key（已配置，建议接手后自行注册并轮换）。留空或 `enabled:false` 时自动降级为规则引擎。
- `server`：host/port（默认 127.0.0.1:8000）。
- `cache`：quote_ttl=3s / kline_ttl=30m / news_ttl=30m。
- `discipline`：chase_high_pct=10（短期涨幅超此值标记「严禁追高」）、stop_loss_pct=8（默认止损参考）。
- 前端「⚙️ 设置」页通过 `GET/POST /api/config` 读写 `ai` 段。

---

## 8. 项目进度与路线图

- **Phase 1**（数据接入 + 自选 + K线/净值 + 指标 + AI 卡 + 新闻）：完成。
- **Phase 2**（多角色 AI + 自动日报 + 设置页）：完成。
- **Phase 3**（选股 / 回测 / 模拟盘）：完成。
- **Phase 4**（实时盘口 + 行业维度 + 估值图 + 标准K线 + 智能选基金 + 爱弥斯皮肤）：完成。
- **后续路线**：P5 自动交易（实盘下单，需券商 API/模拟盘先行验证，风险高，建议谨慎推进）。

---

## 9. 接手后建议做的 5 件事

1. **注册自己的 DeepSeek key** 填入 `config.yaml`，并轮换原 key（原 key 已写入文件，存在泄露风险）。
2. **跑一次 `/api/universe/refresh`** 重建全A 快照（首次或数据过期时），前端「选股」页也有「🔄 重建全A快照」按钮。
3. **验证皮肤**：打开页面确认 `data-skin="aomi"`、底盘口每 3 秒刷新、详情页三段式布局正常。
4. **看 `UI_SKIN_PLAN.md`**：了解皮肤设计意图与后续可扩展点（如更多花纹/动效/立绘槽）。
5. **守住两条红线**：① 前端资源全本地化，勿回退 CDN；② A股 红涨绿跌 `.up`/`.down` 不可改。

---

## 10. 相关文档位置

| 文件 | 内容 |
|---|---|
| `D:\StockPilot\HANDOVER.md` | 本文（项目交接总览） |
| `D:\StockPilot\UI_SKIN_PLAN.md` | 爱弥斯皮肤设计计划（确认稿） |
| `D:\StockPilot\README.md` | 早期项目说明 |
| `D:\StockPilot\frontend\skins\aomi\README.txt` | 立绘背景槽位使用说明 |
| `C:\Users\22091\WorkBuddy\2026-07-23-13-41-56\.workbuddy\memory\MEMORY.md` | 长期项目记忆（架构/皮肤/数据源坑） |
| `C:\Users\22091\WorkBuddy\2026-07-23-13-41-56\.workbuddy\memory\2026-07-25.md` | 本日工作日志 |

> 注：上面的 `memory/` 路径是开发会话的工作记忆，方便追溯决策；正式交付可一并归档或按需删减。
