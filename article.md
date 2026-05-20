# 用 QVeris 把财报电话会逐字稿变成可追溯的投研线索

![把闲散的财报电话会文本转成结构化投研线索](assets/cover_earnings_call_signal.png)

这是一篇第三方实践记录。

我看到 QVeris 已经接入了财报电话会逐字稿相关能力后，做了一个小程序：给定一组股票代码，程序先通过 QVeris 搜索可用工具，再调用逐字稿日期和正文接口，最后把几万字的 transcript 转成跨公司、跨季度、可追溯的主题信号。

它不是投资建议，也不是自动写研报。它解决的是一个更靠前、更具体的问题：当分析师面对多家公司、多期电话会时，如何快速发现值得继续追问的主题，并且保留每个结论背后的原文证据。

## 程序能做什么

- 自动发现并调用 QVeris 上的财报电话会工具。
- 拉取 AAPL、NVDA、TSM 等公司的最近若干期 earnings call transcript。
- 按 AI、Margin、Guidance、China、Capex、Supply Chain、Pricing、Competition 等主题做跨公司对比。
- 输出每个主题的提及次数、每千词频率、风险/机会语境和季度变化。
- 区分管理层主动叙述、分析师追问和管理层对问题的回应。
- 可选通过 QVeris 接入电话会后股价变化，作为市场反应背景。
- 生成 `llm_review_pack.json`，方便把证据台账交给 LLM 生成复核问题，但仍保留原文证据链。
- 保留证据台账 CSV，方便回到原文复核。

## 一次真实运行

我用 AAPL 和 NVDA 各取最近两个季度，跑出了 4 份逐字稿：

| 公司 | 期间 | 日期 |
|---|---|---|
| AAPL | FY2026 Q2 | 2026-04-30 |
| AAPL | FY2026 Q1 | 2026-01-29 |
| NVDA | FY2026 Q4 | 2026-02-25 |
| NVDA | FY2026 Q3 | 2025-11-19 |

主题结果里，AI 是最强信号，共 210 次提及，由 NVDA 领先；Margin 和 Guidance 则主要由 AAPL 贡献。更有用的是，程序会把最新季度和上一季度做标准化对比，例如 NVDA 的 AI 主题从每千词 10.555 次降到 8.811 次，AAPL 的 Margin 从每千词 1.908 次升到 2.236 次。

这些数字本身不构成结论，但它们很适合生成下一步问题：

- NVDA 的 AI 主题降温，是因为叙述重心变化，还是电话会结构变化？
- AAPL 的 Margin 主题升温，来自管理层主动解释，还是分析师追问压力？
- Guidance 相关风险语境是否集中在某些具体业务线？

## 为什么要保留证据台账

投研分析里最怕的是“看起来像结论，但不知道从哪里来的结论”。这个 demo 会生成 `evidence_ledger.csv`，每一行都包含：

- 公司和季度
- 命中的主题和关键词
- 说话人
- 风险/机会/中性标签
- 原文片段

这样后续无论是人工复核、做图表，还是接入内部投研流程，都不用重新从几万字文本里定位出处。

## 电话会议内容是如何获取的

市场上下文用的是 `financialmodelingprep.historical_price_eod.light.retrieve.v1.3f860211`，但它只是后续补充背景。这个 demo 最核心的数据源是 earnings call transcript，本身也是通过 QVeris 获取的。

程序没有直接硬编码外部接口地址，而是先让 QVeris 搜索“电话会日期”和“电话会正文”两类工具：

| 数据 | QVeris 工具 | 参数 | 作用 |
|---|---|---|---|
| 电话会日期列表 | `financialmodelingprep.stable.earningcalltranscriptdates.retrieve.v1.34503129` | `symbol` | 查询某家公司有哪些可用的财报电话会期次。 |
| 电话会逐字稿正文 | `financialmodelingprep.stable.earningcalltranscript.retrieve.v1.5db0c651` | `symbol`, `year`, `quarter` | 拉取指定公司、年份、季度的 earnings call transcript 内容。 |

实际流程是：

1. 先搜索工具：用自然语言查询 `Financial Modeling Prep Transcripts Dates By Symbol earnings call transcript dates` 和 `Financial Modeling Prep Earnings Transcript company earnings call content year quarter`。
2. 再查期次：对每个股票代码调用 transcript dates 工具，例如输入 `AAPL`，返回可用的 fiscal year、quarter 和日期。
3. 选取最近 N 个季度：程序按用户传入的 `--quarters` 截取最近几个期次。
4. 拉取正文：对每个期次调用 transcript content 工具，传入 `symbol/year/quarter`。
5. 分析正文：拿到 `content` 字段后，程序再做说话人识别、Q&A 分段、主题命中、风险/机会语境和证据台账。

这也是为什么文章里强调“可追溯”：报告不只展示主题统计，还会记录 QVeris 搜索命中的 tool、执行结果、`execution_id`、cost，以及每条主题信号对应的原文片段。

## 如何参考微信公众号文章

这篇 demo 不是照着公众号文章复述一遍，而是把文章里的产品思路转成一个可以运行的第三方实践。参考方式大致是：

- 先提取文章里的核心主张：QVeris 的价值不只是“有很多 API”，而是可以通过自然语言搜索工具、理解工具用途、再执行真实调用。
- 再选一个读者容易理解、也能展示完整链路的场景：财报电话会逐字稿天然适合做“搜索工具 → 调用数据 → 结构化分析 → 留存证据”的样例。
- 然后把文章中的抽象能力落到具体产物：命令行程序、网页 dashboard、HTML 报告、CSV 证据台账、在线 Live Run。
- 最后用真实运行结果验证：不是写一篇概念文章，而是把 QVeris 的 search 和 execute 真正接进程序，能看到 tool_id、execution_id、cost 和返回数据。

换句话说，公众号文章提供的是“为什么 QVeris 适合做 API Agent 基础设施”的方向；这个 demo 做的是“拿一个真实投研问题，把这条路径跑通”。

## 运行方式

```bash
uv sync
cp .env.example .env
uv run earnings-signal \
  --symbols AAPL,NVDA,TSM \
  --quarters 2 \
  --theme-set extended \
  --themes AI,Margin,Guidance,SupplyChain,Pricing,Competition \
  --market-context
```

输出文件：

- `earnings_call_signal_report.md`
- `earnings_call_signal_report.json`
- `theme_matrix.csv`
- `evidence_ledger.csv`
- `market_context.csv`
- `llm_review_pack.json`

代码地址：

https://github.com/ax2/qveris-earnings-call-signal-demo

在线测试地址：

http://172.16.10.53:18092/

## 这个程序是如何实现的

这个 demo 的实现思路并不复杂：先把“找数据接口”和“调用数据接口”交给 QVeris，再把精力放到投研工作流本身。程序内部没有硬编码某个固定接口，而是先用自然语言搜索可用工具，再根据搜索结果选择最合适的 tool 执行。

核心链路可以拆成五步：

1. 搜索工具：用 QVeris `/search` 搜索财报电话会日期、逐字稿、历史价格、基础财务指标和新闻类工具。
2. 执行工具：拿到 `search_id` 和 `tool_id` 后，通过 `/tools/execute` 拉取真实数据。
3. 结构化清洗：把逐字稿拆成说话人、管理层/分析师、prepared remarks / Q&A 等结构。
4. 主题识别：按 AI、Margin、Guidance、Supply Chain、Pricing、Competition 等主题统计提及次数、每千词频率和风险/机会语境。
5. 证据留存：把所有命中片段写入 `evidence_ledger.csv`，同时生成 Markdown、JSON、CSV 和网页报告。

电话会议正文的获取是这条链路的第一性数据来源：先用 `financialmodelingprep.stable.earningcalltranscriptdates.retrieve.v1.34503129` 找到可用期次，再用 `financialmodelingprep.stable.earningcalltranscript.retrieve.v1.5db0c651` 按 `symbol/year/quarter` 拉取逐字稿正文。市场价格、基础面和新闻都是在逐字稿分析完成之后补进来的上下文。

这里有几个关键概念：

| 概念 | 作用 |
|---|---|
| Tool discovery | 不预设具体 API，而是让 QVeris 根据自然语言需求返回候选工具。 |
| Search ID | 搜索结果和后续执行之间的关联 ID，执行工具时需要带上。 |
| Evidence ledger | 每一条分析信号都保留原文片段、说话人、主题和上下文，避免只有结论没有出处。 |
| Context enrichment | 电话会内容之外，再补充市场表现、基础面指标和新闻背景。 |
| Live Run | 网页上实时触发 QVeris search + execute，验证程序不是静态报告。 |

整个开发过程基本都由 Codex 完成。我给 Codex 的指令不是“一次性写完程序”，而是按阶段不断收敛：

```text
阅读我们官微的文章，参照这个文章实现一个有意义的程序，需要有实际效果。代码单独放一个仓库，可以在 yswx 下面建一个 demos 目录，里面放独立 demo，然后推送到个人账号。
```

这一步确定了项目方向：做一个能把财报电话会逐字稿转成结构化投研线索的 demo。Codex 先搭出 Python 项目、QVeris 客户端、分析器和命令行入口。

```text
按文章最终的可以继续扩展的方向扩展 qveris-earnings-call-signal-demo。
不要使用 Yahoo Finance chart 接口。
```

这一步把程序从“只分析 transcript”扩展成完整上下文版本。因为明确要求不要使用 Yahoo Finance chart 接口，市场数据改成通过 QVeris 搜索并调用市场数据工具获取。

```text
按新的程序进行截图，并更新文档。
继续按“下一步还可以继续做什么”里面说的完善这个程序，按需截图并更新文章。另外，代码增加 LICENSE，使用 MIT 授权。
```

这一步补齐了截图、报告、LICENSE 和文章内容。Codex 不是只写代码，也负责运行程序、生成输出文件、截取页面、更新文档。

```text
在 testlab 部署这个程序。
除了 Markdown Report 的内容，还可以增加一个 Report 按钮，直接显示 HTML 格式的页面。更新代码、文档并同步部署到 testlab。
```

这一步把 demo 从命令行程序变成可访问的网页应用。Codex 增加了 FastAPI 服务、首页 dashboard、HTML 报告页、截图页和 systemd 用户服务。

```text
这个程序看上去并不像是实时在调用 QVeris 的接口？
点击 Live Run 之后一直处于 Running 状态，经过一段时间后显示 Run failed: Internal Server Error，也不清楚什么问题。
```

这一步推动程序补上 Live Run。Codex 增加了前端表单和 `/run` 接口，让页面可以真实触发 QVeris 调用。后来发现 testlab 直连 `qveris.ai` 超时，服务进程需要走本机代理，于是又补了 systemd 代理环境，并把后端错误从裸 500 改成带 `error/message/hint` 的 502 JSON，方便定位问题。

这个过程里比较有价值的经验是：AI 辅助开发适合拆成连续的小闭环。每一轮都让 Codex 做一件具体的事：实现、运行、截图、部署、测试、看日志、修正错误、更新文章。这样最后得到的不是一段孤立代码，而是一个有代码仓库、有在线地址、有运行记录、有文档说明、也能继续迭代的完整样例。

## 可以继续扩展的方向

这个程序已经补上了第一批扩展：更多主题词库、发言来源分类、通过 QVeris 获取的电话会后价格背景和 LLM 复核包。后续还可以继续扩展：

- 引入财务指标和新闻数据，观察电话会主题变化、基本面变化和外部事件之间的关系。
- 用更细的模型分类替代轻量规则，例如把 risk/opportunity 进一步拆成需求、供给、费用、监管、竞争等维度。
- 把同一公司的多季度主题变化做成长期时间序列。
- 对 evidence ledger 做人工标注，形成可评估的投研语义分类样本。

真正有价值的不是把逐字稿总结成几段话，而是把数据发现、调用、对比和证据留存这一整条链路跑通。
