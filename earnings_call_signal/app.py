from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .analyzer import DEFAULT_THEMES, EarningsCallSignalAnalyzer, select_themes, render_markdown, write_outputs

app = FastAPI(title="QVeris Earnings Call Signal Demo")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")


class AnalyzeRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "NVDA", "TSM"])
    quarters: int = Field(default=2, ge=1, le=8)
    theme_set: str = "extended"
    themes: list[str] | None = None
    market_context: bool = False
    fundamentals_context: bool = False
    news_context: bool = False
    full_context: bool = False
    write_files: bool = True


def _theme_subset(names: list[str] | None, theme_set: str) -> dict[str, list[str]]:
    if not names:
        return select_themes(None, theme_set=theme_set)
    selected = select_themes(names, theme_set=theme_set)
    return selected or DEFAULT_THEMES


def _load_latest_report() -> dict[str, Any] | None:
    report_path = Path("outputs/earnings_call_signal_report.json")
    if not report_path.exists():
        return None
    return json.loads(report_path.read_text(encoding="utf-8"))


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _fmt_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(number) >= 1_000_000_000:
        return f"${number / 1_000_000_000:,.1f}B"
    return f"{number:,.0f}"


def _dashboard_html(report: dict[str, Any]) -> str:
    brief = report.get("research_brief") or {}
    portfolio = report.get("portfolio_view") or {}
    totals = portfolio.get("theme_totals") or {}
    analyses = report.get("analyses") or []
    evidence_rows = sum(
        int((theme_payload or {}).get("mentions") or 0)
        for analysis in analyses
        for theme_payload in (analysis.get("themes") or {}).values()
    )
    output_count = len(list(Path("outputs").glob("*")))
    max_theme_count = max([int(value or 0) for value in totals.values()] or [1])

    theme_bars = "\n".join(
        f"""
        <div class="bar-row">
          <div class="bar-label">{_esc(theme)}</div>
          <div class="bar-track"><span style="width:{int(int(count or 0) / max_theme_count * 100)}%"></span></div>
          <div class="bar-value">{_esc(count)}</div>
        </div>
        """
        for theme, count in list(totals.items())[:8]
    )
    questions = "\n".join(
        f"<li>{_esc(question)}</li>" for question in (brief.get("diligence_questions") or [])[:8]
    )
    timeline_rows = "\n".join(
        f"""
        <tr>
          <td>{_esc(row.get("symbol"))}</td>
          <td>{_esc(row.get("period"))}</td>
          <td>{_esc(row.get("date"))}</td>
          <td>{_esc(row.get("strongest_theme"))}</td>
          <td class="num">{_esc(row.get("strongest_theme_mentions"))}</td>
          <td class="num">{_esc(row.get("next_return_pct"))}%</td>
          <td class="num">{_esc(row.get("latest_gross_margin_pct"))}%</td>
          <td class="num">{_esc(row.get("latest_operating_margin_pct"))}%</td>
        </tr>
        """
        for row in report.get("research_timeline") or []
    )
    fundamentals_rows = "\n".join(
        f"""
        <tr>
          <td>{_esc(row.get("symbol"))}</td>
          <td>{_esc(row.get("fiscal_year"))}</td>
          <td class="num">{_fmt_number(row.get("revenue"))}</td>
          <td class="num">{_esc(row.get("gross_margin_pct"))}%</td>
          <td class="num">{_esc(row.get("operating_margin_pct"))}%</td>
          <td class="num">{_esc(row.get("return_on_invested_capital_pct"))}%</td>
        </tr>
        """
        for row in (report.get("fundamentals_context") or [])[:6]
        if row.get("status") != "unavailable"
    )
    news_summary = report.get("news_summary") or {}
    news_cards = "\n".join(
        f"""
        <article class="news-card">
          <div class="eyebrow">{_esc(symbol)}</div>
          <h3>{_esc(item.get("title"))}</h3>
          <p>{_esc(item.get("published_at"))} · {_esc(item.get("publisher"))}</p>
          <span>{_esc(item.get("topics"))}</span>
        </article>
        """
        for symbol, items in (news_summary.get("latest_titles_by_symbol") or {}).items()
        for item in items[:2]
    )
    screenshots = [
        ("Run overview", "screenshot_dashboard_overview.png"),
        ("Context matrix", "screenshot_context_matrix.png"),
        ("Research timeline", "screenshot_research_timeline.png"),
        ("Semantic annotation", "screenshot_semantic_annotation.png"),
        ("Market context", "screenshot_market_context_qveris.png"),
        ("LLM review pack", "screenshot_llm_review_pack.png"),
    ]
    screenshot_cards = "\n".join(
        f"""
        <a class="shot" href="/assets/screenshots/{filename}" target="_blank">
          <img src="/assets/screenshots/{filename}" alt="{_esc(title)}" />
          <span>{_esc(title)}</span>
        </a>
        """
        for title, filename in screenshots
        if (Path("assets/screenshots") / filename).exists()
    )

    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>QVeris Earnings Call Signal Demo</title>
        <style>
          :root {{
            color-scheme: light;
            --bg: #f4f7fb;
            --panel: #ffffff;
            --ink: #172033;
            --muted: #647084;
            --line: #dfe6ef;
            --blue: #2563eb;
            --teal: #0f766e;
            --amber: #d97706;
            --violet: #7c3aed;
          }}
          * {{ box-sizing: border-box; }}
          body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }}
          main {{ max-width: 1320px; margin: 0 auto; padding: 34px 24px 56px; }}
          header {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 24px; }}
          h1 {{ font-size: 42px; line-height: 1.05; margin: 0 0 10px; letter-spacing: 0; }}
          h2 {{ font-size: 20px; margin: 0 0 18px; }}
          h3 {{ font-size: 15px; line-height: 1.35; margin: 0; }}
          p {{ color: var(--muted); line-height: 1.55; margin: 0; }}
          a {{ color: inherit; }}
          .actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
          .button {{ border: 1px solid var(--line); background: var(--panel); border-radius: 8px; padding: 10px 13px; text-decoration: none; font-size: 14px; color: var(--ink); }}
          .grid {{ display: grid; gap: 18px; }}
          .metrics {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 26px 0 18px; }}
          .two {{ grid-template-columns: 1fr 1fr; }}
          .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 22px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03); }}
          .metric span {{ color: var(--muted); font-size: 14px; }}
          .metric strong {{ display: block; font-size: 30px; margin-top: 8px; }}
          .bar-row {{ display: grid; grid-template-columns: 132px 1fr 54px; align-items: center; gap: 14px; margin: 16px 0; }}
          .bar-track {{ height: 28px; border-radius: 999px; background: #eaf0f6; overflow: hidden; }}
          .bar-track span {{ display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--blue), var(--teal)); }}
          .bar-value, .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
          ol {{ margin: 0; padding-left: 22px; }}
          li {{ margin: 0 0 13px; color: #273449; line-height: 1.45; }}
          table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
          th {{ color: #334155; text-align: left; background: #eef3f8; font-weight: 600; }}
          th, td {{ padding: 12px 13px; border-bottom: 1px solid #eef2f6; }}
          tbody tr:nth-child(even) {{ background: #fafcff; }}
          .news {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
          .news-card {{ border: 1px solid var(--line); border-radius: 10px; padding: 15px; background: #fff; min-height: 150px; }}
          .eyebrow {{ color: var(--teal); font-size: 12px; font-weight: 700; margin-bottom: 10px; }}
          .news-card p {{ font-size: 12px; margin: 10px 0; }}
          .news-card span {{ display: inline-block; font-size: 12px; color: var(--blue); background: #eff6ff; padding: 4px 7px; border-radius: 999px; }}
          .screenshots {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
          .shot {{ display: block; background: #fff; border: 1px solid var(--line); border-radius: 12px; overflow: hidden; text-decoration: none; }}
          .shot img {{ display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: cover; border-bottom: 1px solid var(--line); }}
          .shot span {{ display: block; padding: 12px 14px; font-size: 14px; color: #273449; }}
          .section {{ margin-top: 18px; }}
          code {{ background: #eef3f8; border-radius: 6px; padding: 2px 6px; }}
          @media (max-width: 960px) {{
            header {{ display: block; }}
            .metrics, .two, .news, .screenshots {{ grid-template-columns: 1fr; }}
            h1 {{ font-size: 34px; }}
          }}
        </style>
      </head>
      <body>
        <main>
          <header>
            <div>
              <h1>QVeris Earnings Call Signal Demo</h1>
              <p>{_esc(brief.get("headline"))} Generated at <code>{_esc(report.get("generated_at"))}</code>.</p>
            </div>
            <nav class="actions">
              <a class="button" href="/screenshots">Screenshots</a>
              <a class="button" href="/report">Report</a>
              <a class="button" href="/report/markdown">Markdown report</a>
              <a class="button" href="/health">Health</a>
            </nav>
          </header>

          <section class="grid metrics">
            <div class="panel metric"><span>Transcripts</span><strong style="color:var(--blue)">{_esc((brief.get("coverage") or {}).get("transcripts"))}</strong></div>
            <div class="panel metric"><span>Evidence rows</span><strong style="color:var(--teal)">{evidence_rows}</strong></div>
            <div class="panel metric"><span>Output files</span><strong style="color:var(--amber)">{output_count}</strong></div>
            <div class="panel metric"><span>Elapsed</span><strong style="color:var(--violet)">{_esc(report.get("elapsed_s"))}s</strong></div>
          </section>

          <section class="grid two">
            <div class="panel">
              <h2>Theme Strength</h2>
              {theme_bars}
            </div>
            <div class="panel">
              <h2>Follow-up Questions</h2>
              <ol>{questions}</ol>
            </div>
          </section>

          <section class="panel section">
            <h2>Research Timeline</h2>
            <table>
              <thead><tr><th>Symbol</th><th>Period</th><th>Date</th><th>Theme</th><th class="num">Mentions</th><th class="num">Next day</th><th class="num">Gross margin</th><th class="num">Op margin</th></tr></thead>
              <tbody>{timeline_rows}</tbody>
            </table>
          </section>

          <section class="panel section">
            <h2>Fundamentals Context</h2>
            <table>
              <thead><tr><th>Symbol</th><th>FY</th><th class="num">Revenue</th><th class="num">Gross margin</th><th class="num">Operating margin</th><th class="num">ROIC</th></tr></thead>
              <tbody>{fundamentals_rows}</tbody>
            </table>
          </section>

          <section class="section">
            <h2>Latest News Context</h2>
            <div class="grid news">{news_cards}</div>
          </section>

          <section class="section">
            <h2>Article Screenshots</h2>
            <div class="grid screenshots">{screenshot_cards}</div>
          </section>
        </main>
      </body>
    </html>
    """


def _table_rows(rows: list[dict[str, Any]], fields: list[tuple[str, str]], *, limit: int | None = None) -> str:
    selected = rows[:limit] if limit else rows
    return "\n".join(
        "<tr>"
        + "".join(f"<td>{_esc(row.get(field))}</td>" for field, _label in fields)
        + "</tr>"
        for row in selected
    )


def _report_html(report: dict[str, Any]) -> str:
    brief = report.get("research_brief") or {}
    portfolio = report.get("portfolio_view") or {}
    qveris = report.get("qveris") or {}
    tools = qveris.get("tools") or {}
    analyses = report.get("analyses") or []
    themes = list((report.get("themes") or {}).keys())

    questions = "\n".join(
        f"<li>{_esc(question)}</li>" for question in brief.get("diligence_questions") or []
    )
    tool_rows = "\n".join(
        [
            f"<tr><td>Transcript dates</td><td><code>{_esc(tools.get('dates_tool_id'))}</code></td><td>{_esc(tools.get('dates_tool_rank'))}</td></tr>",
            f"<tr><td>Transcript content</td><td><code>{_esc(tools.get('transcript_tool_id'))}</code></td><td>{_esc(tools.get('transcript_tool_rank'))}</td></tr>",
        ]
    )
    totals = portfolio.get("theme_totals") or {}
    labels = portfolio.get("theme_labels") or {}
    source_contexts = portfolio.get("theme_source_contexts") or {}
    leaders = portfolio.get("theme_leaders") or {}
    theme_rows = "\n".join(
        f"""
        <tr>
          <td>{_esc(theme)}</td>
          <td class="num">{_esc(count)}</td>
          <td class="num">{_esc((labels.get(theme) or {}).get("opportunity", 0))}</td>
          <td class="num">{_esc((labels.get(theme) or {}).get("risk", 0))}</td>
          <td class="num">{_esc((source_contexts.get(theme) or {}).get("management_active", 0))}</td>
          <td class="num">{_esc((source_contexts.get(theme) or {}).get("analyst_prompted", 0))}</td>
          <td>{_esc(leaders.get(theme, "-"))}</td>
        </tr>
        """
        for theme, count in totals.items()
    )
    momentum_rows = _table_rows(
        portfolio.get("theme_momentum") or [],
        [
            ("symbol", "Symbol"),
            ("theme", "Theme"),
            ("latest_period", "Latest"),
            ("previous_period", "Previous"),
            ("latest_per_1k", "Latest / 1k"),
            ("previous_per_1k", "Previous / 1k"),
            ("delta_per_1k", "Delta"),
        ],
        limit=16,
    )
    period_rows = "\n".join(
        f"""
        <tr>
          <td>{_esc(row.get("symbol"))}</td>
          <td>{_esc(row.get("period"))}</td>
          <td>{_esc(row.get("date"))}</td>
          <td class="num">{_esc(row.get("word_count_estimate"))}</td>
          <td class="num">{_esc(row.get("speaker_count"))}</td>
          {''.join(f'<td class="num">{_esc(((row.get("themes") or {}).get(theme) or {}).get("mentions", 0))}</td>' for theme in themes)}
        </tr>
        """
        for row in analyses
    )
    theme_head_cells = "".join(f"<th class=\"num\">{_esc(theme)}</th>" for theme in themes)
    timeline_rows = _table_rows(
        report.get("research_timeline") or [],
        [
            ("symbol", "Symbol"),
            ("period", "Period"),
            ("date", "Date"),
            ("strongest_theme", "Strongest theme"),
            ("strongest_theme_mentions", "Mentions"),
            ("next_return_pct", "Next return"),
            ("latest_gross_margin_pct", "Gross margin"),
            ("latest_operating_margin_pct", "Op margin"),
        ],
    )
    fundamentals_rows = _table_rows(
        [row for row in report.get("fundamentals_context") or [] if row.get("status") != "unavailable"],
        [
            ("symbol", "Symbol"),
            ("fiscal_year", "FY"),
            ("revenue", "Revenue"),
            ("gross_margin_pct", "Gross margin"),
            ("operating_margin_pct", "Op margin"),
            ("return_on_invested_capital_pct", "ROIC"),
            ("capex_to_revenue_pct", "Capex / revenue"),
        ],
    )
    news_rows = _table_rows(
        [row for row in report.get("news_context") or [] if row.get("status") != "unavailable"],
        [
            ("symbol", "Symbol"),
            ("published_at", "Published"),
            ("publisher", "Publisher"),
            ("news_topics", "Topics"),
            ("title", "Title"),
        ],
        limit=16,
    )
    evidence_items = "\n".join(
        f"""
        <article class="evidence">
          <div>{_esc(item.get("symbol"))} · {_esc(item.get("period"))} · {_esc(item.get("theme"))} · {_esc(item.get("label"))} / {_esc(item.get("source_context"))}</div>
          <p>{_esc(item.get("speaker"))}: {_esc(item.get("snippet"))}</p>
        </article>
        """
        for row in analyses
        for theme_payload in (row.get("themes") or {}).values()
        for item in (theme_payload.get("snippets") or [])[:1]
    )

    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Earnings Call Signal Report</title>
        <style>
          :root {{ --bg:#f4f7fb; --panel:#fff; --ink:#172033; --muted:#647084; --line:#dfe6ef; --blue:#2563eb; --teal:#0f766e; }}
          * {{ box-sizing: border-box; }}
          body {{ margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); }}
          main {{ max-width: 1180px; margin:0 auto; padding:34px 24px 64px; }}
          header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:18px; margin-bottom:22px; }}
          h1 {{ font-size:40px; line-height:1.08; margin:0 0 10px; letter-spacing:0; }}
          h2 {{ font-size:22px; margin:0 0 16px; }}
          p {{ margin:0; color:var(--muted); line-height:1.55; }}
          code {{ background:#eef3f8; border-radius:6px; padding:2px 6px; word-break:break-all; }}
          .actions {{ display:flex; gap:10px; flex-wrap:wrap; }}
          .button {{ border:1px solid var(--line); background:var(--panel); border-radius:8px; padding:10px 13px; text-decoration:none; color:var(--ink); font-size:14px; }}
          .section {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:22px; margin-top:18px; overflow:auto; }}
          .brief {{ border-left:4px solid var(--blue); }}
          ol {{ margin:14px 0 0; padding-left:24px; }}
          li {{ margin:0 0 10px; line-height:1.5; }}
          table {{ width:100%; border-collapse:collapse; font-size:14px; }}
          th {{ text-align:left; background:#eef3f8; color:#334155; font-weight:600; }}
          th, td {{ padding:11px 12px; border-bottom:1px solid #eef2f6; vertical-align:top; }}
          tbody tr:nth-child(even) {{ background:#fafcff; }}
          .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
          .evidence {{ border:1px solid var(--line); border-radius:10px; padding:14px; margin:12px 0; background:#fff; }}
          .evidence div {{ color:var(--teal); font-weight:700; font-size:13px; margin-bottom:8px; }}
          .evidence p {{ color:#273449; }}
          @media (max-width: 900px) {{ header {{ display:block; }} .actions {{ margin-top:16px; }} h1 {{ font-size:32px; }} }}
        </style>
      </head>
      <body>
        <main>
          <header>
            <div>
              <h1>Earnings Call Signal Report: {_esc(", ".join(report.get("symbols") or []))}</h1>
              <p>Generated at <code>{_esc(report.get("generated_at"))}</code> with QVeris search + execute. Elapsed: <code>{_esc(report.get("elapsed_s"))}s</code>.</p>
            </div>
            <nav class="actions">
              <a class="button" href="/">Dashboard</a>
              <a class="button" href="/report/markdown">Markdown</a>
              <a class="button" href="/screenshots">Screenshots</a>
            </nav>
          </header>

          <section class="section brief">
            <h2>Research Brief</h2>
            <p><b>{_esc(brief.get("headline"))}</b></p>
            <ol>{questions}</ol>
          </section>

          <section class="section">
            <h2>QVeris Tool Discovery</h2>
            <table><thead><tr><th>Tool</th><th>Tool ID</th><th class="num">Search rank</th></tr></thead><tbody>{tool_rows}</tbody></table>
          </section>

          <section class="section">
            <h2>Portfolio Theme View</h2>
            <table><thead><tr><th>Theme</th><th class="num">Total</th><th class="num">Opportunity</th><th class="num">Risk</th><th class="num">Management active</th><th class="num">Analyst prompted</th><th>Leader</th></tr></thead><tbody>{theme_rows}</tbody></table>
          </section>

          <section class="section">
            <h2>Theme Momentum</h2>
            <table><thead><tr><th>Symbol</th><th>Theme</th><th>Latest</th><th>Previous</th><th>Latest / 1k</th><th>Previous / 1k</th><th>Delta</th></tr></thead><tbody>{momentum_rows}</tbody></table>
          </section>

          <section class="section">
            <h2>Period Summaries</h2>
            <table><thead><tr><th>Symbol</th><th>Period</th><th>Date</th><th class="num">Words</th><th class="num">Speakers</th>{theme_head_cells}</tr></thead><tbody>{period_rows}</tbody></table>
          </section>

          <section class="section">
            <h2>Research Timeline</h2>
            <table><thead><tr><th>Symbol</th><th>Period</th><th>Date</th><th>Strongest theme</th><th>Mentions</th><th>Next return</th><th>Gross margin</th><th>Op margin</th></tr></thead><tbody>{timeline_rows}</tbody></table>
          </section>

          <section class="section">
            <h2>Fundamentals Context</h2>
            <table><thead><tr><th>Symbol</th><th>FY</th><th>Revenue</th><th>Gross margin</th><th>Op margin</th><th>ROIC</th><th>Capex / revenue</th></tr></thead><tbody>{fundamentals_rows}</tbody></table>
          </section>

          <section class="section">
            <h2>News Context</h2>
            <table><thead><tr><th>Symbol</th><th>Published</th><th>Publisher</th><th>Topics</th><th>Title</th></tr></thead><tbody>{news_rows}</tbody></table>
          </section>

          <section class="section">
            <h2>Evidence Snippets</h2>
            {evidence_items}
          </section>
        </main>
      </body>
    </html>
    """


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    report = _load_latest_report()
    if report:
        return _dashboard_html(report)
    return """
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>QVeris Earnings Call Signal Demo</title>
        <style>
          body { margin: 0; font-family: Inter, Arial, sans-serif; background: #f7f8fb; color: #172033; }
          main { max-width: 920px; margin: 0 auto; padding: 56px 24px; }
          h1 { font-size: 42px; line-height: 1.1; margin: 0 0 16px; }
          p { font-size: 18px; line-height: 1.6; color: #4b5565; }
          code { background: #eef1f6; padding: 2px 6px; border-radius: 6px; }
          .panel { background: white; border: 1px solid #e4e8f0; border-radius: 8px; padding: 20px; }
        </style>
      </head>
      <body>
        <main>
          <h1>Earnings Call Signal Analyzer</h1>
          <p>Search QVeris for earnings-call transcript tools, execute them, and turn long transcripts into a source-backed research brief with theme momentum, evidence ledgers, and optional market, fundamentals, and news context.</p>
          <div class="panel">
            <p>Try <code>POST /run</code> with JSON: <code>{"symbols":["AAPL","NVDA"],"quarters":2,"theme_set":"extended","full_context":true}</code></p>
            <p>Try <code>POST /run/markdown</code> for a Markdown report.</p>
          </div>
        </main>
      </body>
    </html>
    """


@app.get("/screenshots", response_class=HTMLResponse)
def screenshots() -> str:
    report = _load_latest_report() or {
        "research_brief": {"headline": "Generated screenshot gallery"},
        "analyses": [],
        "portfolio_view": {},
    }
    html_doc = _dashboard_html(report)
    start = html_doc.find("<section class=\"section\">\n            <h2>Article Screenshots</h2>")
    if start >= 0:
        body = html_doc[start:]
        body = body.split("</main>", 1)[0]
    else:
        body = "<p>No screenshots found.</p>"
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>QVeris Demo Screenshots</title>
        <style>
          body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #f4f7fb; color: #172033; }}
          main {{ max-width: 1320px; margin: 0 auto; padding: 34px 24px 56px; }}
          h1 {{ margin: 0 0 20px; font-size: 38px; }}
          h2 {{ font-size: 22px; margin: 0 0 18px; }}
          .grid {{ display: grid; gap: 18px; grid-template-columns: repeat(3, minmax(0, 1fr)); }}
          .shot {{ display: block; background: #fff; border: 1px solid #dfe6ef; border-radius: 12px; overflow: hidden; text-decoration: none; color: #172033; }}
          .shot img {{ display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: cover; border-bottom: 1px solid #dfe6ef; }}
          .shot span {{ display: block; padding: 12px 14px; font-size: 14px; }}
          @media (max-width: 960px) {{ .grid {{ grid-template-columns: 1fr; }} }}
        </style>
      </head>
      <body><main><h1>Article Screenshots</h1>{body}</main></body>
    </html>
    """


@app.get("/report/markdown", response_class=PlainTextResponse)
def latest_markdown_report() -> str:
    report_path = Path("outputs/earnings_call_signal_report.md")
    if not report_path.exists():
        return "No generated report found. Run POST /run first."
    return report_path.read_text(encoding="utf-8")


@app.get("/report", response_class=HTMLResponse)
def latest_html_report() -> str:
    report = _load_latest_report()
    if not report:
        return """
        <!doctype html>
        <html><body><main><h1>No generated report found</h1><p>Run POST /run first.</p></main></body></html>
        """
    return _report_html(report)


@app.post("/run")
async def run(req: AnalyzeRequest) -> dict[str, object]:
    report = await EarningsCallSignalAnalyzer().run(
        symbols=req.symbols,
        quarters_per_symbol=req.quarters,
        themes=_theme_subset(req.themes, req.theme_set),
        include_market_context=req.market_context or req.full_context,
        include_fundamentals_context=req.fundamentals_context or req.full_context,
        include_news_context=req.news_context or req.full_context,
    )
    if req.write_files:
        report["outputs"] = write_outputs(report, Path("outputs"))
    return report


@app.post("/run/markdown", response_class=PlainTextResponse)
async def run_markdown(req: AnalyzeRequest) -> str:
    report = await EarningsCallSignalAnalyzer().run(
        symbols=req.symbols,
        quarters_per_symbol=req.quarters,
        themes=_theme_subset(req.themes, req.theme_set),
        include_market_context=req.market_context or req.full_context,
        include_fundamentals_context=req.fundamentals_context or req.full_context,
        include_news_context=req.news_context or req.full_context,
    )
    if req.write_files:
        write_outputs(report, Path("outputs"))
    return render_markdown(report)
