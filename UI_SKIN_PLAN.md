# StockPilot · UI 皮肤与设计系统现状(2026-08-01 修订)

> **本文档已修订**:旧版(鸣潮·爱弥斯皮肤计划)为**未落地的计划稿**,与实际代码不符,已废弃。
> 现版本反映**已实施**的 Obsidian 设计系统,并把"皮肤"定位为可叠加的扩展层。

---

## 一、已实施:Obsidian 黑曜石设计系统(frontend-v2)

代码位置:`frontend-v2/src/assets/obsidian.css`(202 行)+ `composables/useLiquidGlass.ts`(261 行)+ `stores/theme.ts` + `components/ParticleCanvas.vue` / `LiquidCanvas.vue`。

### 1. 色彩令牌(CSS 变量,`[data-theme=dark|light]` 双套)
| 令牌 | 暗色 | 说明 |
|---|---|---|
| `--bg-base` | `#080a0f` | 近黑基底 |
| `--bg-surface` | `#0f1218` | 侧栏/面板 |
| `--bg-elevated` | `#161b24` | 卡片 |
| `--bg-overlay` | `#1e2430` / hover `#232a38` | 浮层/悬停 |
| `--accent` | `#c9a962`(金铜) | 主强调 + `--accent-glow` 辉光 |
| `--up` / `--down` | `#f04848` / `#26c966` | **红涨绿跌,双主题不变(硬规则)** |
| 文字 | `#f2f4f7` / `#98a1b0` / `#565f6e` | 主/次/弱三级 |
| 边框 | `rgba(255,255,255,.05/.09/.15)` | 三级细分 |

### 2. 液体玻璃交互(useLiquidGlass)
- **Jelly 弹簧物理**:按压 squash-and-stretch(压扁~6%)+ 释放弹性回弹(wobble),弹簧刚度/阻尼可调
- **光标跟随倾斜**(maxTilt)+ `--glow-x/--glow-y` 鼠标辉光 + `--press` 按压缩放
- **全局粒子总线**:点击/交互发射粒子(金色 hue 42 为主、蓝 hue 200 点缀),上限 150 粒

### 3. 布局(DefaultLayout.vue)
- 左侧固定 sidebar:logo 区(`StockPilot` + subtitle + logo-line)+ **分组导航**(市场 / 策略工具 / 研究 / 合规管理)+ 底部用户区
- 右侧主内容区,视图切换淡入(`animate-in` fadeUp,0.5s)
- 细滚动条(5px),等宽数字字体(JetBrains Mono `.tnum`)

### 4. 主题切换
- Pinia `theme` store,默认**暗色**,`localStorage['sp-theme']` 持久,`data-theme` 切换,0.45s 过渡

---

## 二、与旧计划的差异(为什么废弃爱弥斯)

| 项 | 旧计划(爱弥斯) | 实际(Obsidian) |
|---|---|---|
| 强调色 | 粉 `#ff5ea8` + 蓝紫 `#a274ff` | 金铜 `#c9a962` |
| 背景 | 紫夜空渐变 | 近黑分层 `#080a0f→#161b24` |
| 质感 | 全息渐变网 + 故障扫描线 | 液体玻璃 jelly + 粒子 |
| 状态 | 计划稿,未实施 | **已实施并全站使用**(16 个 view) |

结论:爱弥斯风格从未落地;Obsidian 才是当前真实 UI。

---

## 三、皮肤扩展方案(未来,可选)

现状架构(CSS 变量令牌 + `data-theme`)天然支持**皮肤叠加层**,无需改 JS 绘图逻辑:

1. **皮肤层**:`html[data-skin="aomi"]` 等覆写 `--accent/--bg-*/--particle-color`(参考旧爱弥斯配色或用户新取向),与 theme 正交组合(暗/亮 × 皮肤)。
2. **落地步骤**:
   - P1:设置页加"皮肤切换",`data-skin` 属性 + `spSkin()` 读取变量
   - P2:皮肤专属变量覆写 + 装饰 SVG(本地托管,无 CDN)
   - P3:全站校验令牌生效、红涨绿跌不变、动效遵循 `prefers-reduced-motion`
3. **红涨绿跌硬规则**:`--up/--down` 任何皮肤下保持不变(交易软件红线)。

> 当前无紧急需求;若要做皮肤,建议先出 1-2 套暗色皮肤(如"金色暖调/蓝紫冷调")供选择,不引入第三套完整亮暗体系。
