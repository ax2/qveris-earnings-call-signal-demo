# 用 QVeris 把财报电话会逐字稿变成可追溯的投研线索

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

## 可以继续扩展的方向

这个程序已经补上了第一批扩展：更多主题词库、发言来源分类、通过 QVeris 获取的电话会后价格背景和 LLM 复核包。后续还可以继续扩展：

- 引入财务指标和新闻数据，观察电话会主题变化、基本面变化和外部事件之间的关系。
- 用更细的模型分类替代轻量规则，例如把 risk/opportunity 进一步拆成需求、供给、费用、监管、竞争等维度。
- 把同一公司的多季度主题变化做成长期时间序列。
- 对 evidence ledger 做人工标注，形成可评估的投研语义分类样本。

真正有价值的不是把逐字稿总结成几段话，而是把数据发现、调用、对比和证据留存这一整条链路跑通。
