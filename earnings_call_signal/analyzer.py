from __future__ import annotations

import asyncio
import csv
import json
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import QverisClient

DATES_TOOL_ID = "financialmodelingprep.stable.earningcalltranscriptdates.retrieve.v1.34503129"
TRANSCRIPT_TOOL_ID = "financialmodelingprep.stable.earningcalltranscript.retrieve.v1.5db0c651"

DATES_DISCOVER_QUERY = (
    "Financial Modeling Prep Transcripts Dates By Symbol earnings call transcript dates"
)
TRANSCRIPT_DISCOVER_QUERY = (
    "Financial Modeling Prep Earnings Transcript company earnings call content year quarter"
)

DEFAULT_THEMES: dict[str, list[str]] = {
    "AI": ["AI", "artificial intelligence", "generative AI", "large language model", "LLM"],
    "Margin": ["gross margin", "operating margin", "margin", "profitability"],
    "China": ["China", "Greater China", "Mainland China"],
    "Capex": ["capex", "capital expenditure", "data center", "infrastructure"],
    "Guidance": ["guidance", "outlook", "forecast", "next quarter"],
}

OPPORTUNITY_WORDS = {
    "growth",
    "strong",
    "accelerate",
    "acceleration",
    "demand",
    "opportunity",
    "record",
    "improve",
    "improved",
    "expansion",
    "upside",
    "momentum",
}

RISK_WORDS = {
    "risk",
    "weak",
    "decline",
    "declined",
    "pressure",
    "headwind",
    "uncertain",
    "uncertainty",
    "constraint",
    "shortage",
    "tariff",
    "challenge",
    "challenging",
    "downside",
}


@dataclass(frozen=True)
class Period:
    symbol: str
    year: int
    quarter: int
    date: str

    @property
    def label(self) -> str:
        return f"FY{self.year} Q{self.quarter}"


def _as_list(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if data is None:
        return []
    return [data]


def _result_data(execute_payload: dict[str, Any]) -> Any:
    result = execute_payload.get("result")
    if not isinstance(result, dict):
        return None
    if "data" in result:
        return result["data"]
    raw = result.get("truncated_content")
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return None


def _compile_theme_patterns(themes: dict[str, list[str]]) -> dict[str, re.Pattern[str]]:
    patterns: dict[str, re.Pattern[str]] = {}
    for name, terms in themes.items():
        escaped = [re.escape(term) for term in terms if term.strip()]
        if escaped:
            patterns[name] = re.compile(r"(?i)\b(" + "|".join(escaped) + r")\b")
    return patterns


def _speaker_before(content: str, start: int) -> str | None:
    prefix = content[:start]
    matches = list(re.finditer(r"(?:^|\n)([A-Z][A-Za-z .'\-]{1,70}):\s", prefix))
    if not matches:
        return None
    return matches[-1].group(1).strip()


def _sentence_window(content: str, start: int, end: int, radius: int = 260) -> str:
    left = max(0, start - radius)
    right = min(len(content), end + radius)
    snippet = re.sub(r"\s+", " ", content[left:right].replace("\n", " ")).strip()
    if left > 0:
        snippet = "..." + snippet
    if right < len(content):
        snippet += "..."
    return snippet


def _label_context(text: str) -> str:
    lower = text.lower()
    opportunity_hits = sum(1 for word in OPPORTUNITY_WORDS if re.search(rf"\b{word}\b", lower))
    risk_hits = sum(1 for word in RISK_WORDS if re.search(rf"\b{word}\b", lower))
    if risk_hits > opportunity_hits:
        return "risk"
    if opportunity_hits > risk_hits:
        return "opportunity"
    return "neutral"


def _speaker_role(name: str | None, snippet: str) -> str:
    if not name:
        return "unknown"
    lower_name = name.lower()
    lower_snippet = snippet.lower()
    if "operator" in lower_name:
        return "operator"
    if "?" in snippet or lower_snippet.startswith(("thanks", "thank you", "good afternoon")):
        return "question"
    return "management"


def _per_1k(count: int, words: int) -> float:
    if words <= 0:
        return 0.0
    return round(count * 1000 / words, 3)


def analyze_transcript(
    *,
    period: Period,
    content: str,
    themes: dict[str, list[str]],
    max_snippets_per_theme: int = 4,
) -> dict[str, Any]:
    patterns = _compile_theme_patterns(themes)
    speaker_turns = re.findall(r"(?:^|\n)([A-Z][A-Za-z .'\-]{1,70}):\s", content)
    speaker_counts = Counter(s.strip() for s in speaker_turns)
    word_count = len(re.findall(r"[A-Za-z0-9$%.\-]+", content))

    theme_rows: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, Any]] = []
    for theme, pattern in patterns.items():
        matches = list(pattern.finditer(content))
        labels: Counter[str] = Counter()
        speakers: Counter[str] = Counter()
        snippets: list[dict[str, str]] = []
        for match in matches:
            snippet = _sentence_window(content, match.start(), match.end())
            speaker = _speaker_before(content, match.start()) or "Unknown"
            label = _label_context(snippet)
            role = _speaker_role(speaker, snippet)
            labels[label] += 1
            speakers[speaker] += 1
            row = {
                "symbol": period.symbol,
                "period": period.label,
                "date": period.date,
                "theme": theme,
                "term": match.group(0),
                "speaker": speaker,
                "speaker_role": role,
                "label": label,
                "snippet": snippet,
            }
            evidence.append(row)
            if len(snippets) < max_snippets_per_theme:
                snippets.append(row)

        theme_rows[theme] = {
            "mentions": len(matches),
            "mentions_per_1k_words": _per_1k(len(matches), word_count),
            "labels": dict(labels),
            "top_speakers": speakers.most_common(5),
            "snippets": snippets,
        }

    return {
        "symbol": period.symbol,
        "year": period.year,
        "quarter": period.quarter,
        "period": period.label,
        "date": period.date,
        "char_count": len(content),
        "word_count_estimate": word_count,
        "speaker_count": len(speaker_counts),
        "top_speakers": speaker_counts.most_common(8),
        "themes": theme_rows,
        "evidence": evidence,
    }


class EarningsCallSignalAnalyzer:
    def __init__(self, client: QverisClient | None = None) -> None:
        self.client = client or QverisClient(timeout_s=180)
        self.session_id = str(uuid.uuid4())

    async def _discover(self) -> dict[str, Any]:
        dates_search, transcript_search = await asyncio.gather(
            self.client.search(DATES_DISCOVER_QUERY, limit=10, session_id=self.session_id),
            self.client.search(TRANSCRIPT_DISCOVER_QUERY, limit=10, session_id=self.session_id),
        )
        return {
            "dates_search": dates_search,
            "transcript_search": transcript_search,
            "dates_tool_rank": self._rank_of(dates_search, DATES_TOOL_ID),
            "transcript_tool_rank": self._rank_of(transcript_search, TRANSCRIPT_TOOL_ID),
        }

    @staticmethod
    def _rank_of(search_payload: dict[str, Any], tool_id: str) -> int | None:
        for index, tool in enumerate(search_payload.get("results") or []):
            if tool.get("tool_id") == tool_id:
                return index + 1
        return None

    async def _dates_for_symbol(
        self,
        *,
        symbol: str,
        search_id: str,
        limit: int,
    ) -> tuple[list[Period], dict[str, Any]]:
        execution = await self.client.execute(
            DATES_TOOL_ID,
            search_id=search_id,
            parameters={"symbol": symbol},
            session_id=self.session_id,
            max_response_size=120000,
        )
        periods: list[Period] = []
        for row in _as_list(_result_data(execution)):
            if not isinstance(row, dict):
                continue
            try:
                periods.append(
                    Period(
                        symbol=symbol.upper(),
                        year=int(row["fiscalYear"]),
                        quarter=int(row["quarter"]),
                        date=str(row.get("date") or ""),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return periods[:limit], execution

    async def _transcript_for_period(
        self,
        *,
        period: Period,
        search_id: str,
    ) -> tuple[str, dict[str, Any]]:
        execution = await self.client.execute(
            TRANSCRIPT_TOOL_ID,
            search_id=search_id,
            parameters={
                "symbol": period.symbol,
                "year": str(period.year),
                "quarter": str(period.quarter),
            },
            session_id=self.session_id,
            max_response_size=120000,
        )
        for row in _as_list(_result_data(execution)):
            if isinstance(row, dict) and isinstance(row.get("content"), str):
                return row["content"], execution
        return "", execution

    async def run(
        self,
        *,
        symbols: list[str],
        quarters_per_symbol: int = 2,
        themes: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        clean_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            raise ValueError("At least one symbol is required.")
        quarters_per_symbol = max(1, min(int(quarters_per_symbol), 8))
        theme_map = themes or DEFAULT_THEMES

        discover = await self._discover()
        dates_search_id = discover["dates_search"].get("search_id")
        transcript_search_id = discover["transcript_search"].get("search_id")
        if not dates_search_id or not transcript_search_id:
            raise RuntimeError("QVeris search did not return required search_id values.")

        date_results = await asyncio.gather(
            *[
                self._dates_for_symbol(
                    symbol=symbol,
                    search_id=dates_search_id,
                    limit=quarters_per_symbol,
                )
                for symbol in clean_symbols
            ]
        )

        selected_periods: list[Period] = []
        date_execs: dict[str, dict[str, Any]] = {}
        for symbol, (periods, execution) in zip(clean_symbols, date_results, strict=True):
            selected_periods.extend(periods)
            date_execs[symbol] = _compact_execute_meta(execution)

        transcript_results = await asyncio.gather(
            *[
                self._transcript_for_period(period=period, search_id=transcript_search_id)
                for period in selected_periods
            ]
        )

        analyses: list[dict[str, Any]] = []
        transcript_execs: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for period, (content, execution) in zip(selected_periods, transcript_results, strict=True):
            transcript_execs.append({"period": period.__dict__, **_compact_execute_meta(execution)})
            if not content:
                missing.append(period.__dict__)
                continue
            analyses.append(analyze_transcript(period=period, content=content, themes=theme_map))

        portfolio_view = build_portfolio_view(analyses)
        return {
            "demo": "qveris-earnings-call-signal-demo",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_s": round(time.monotonic() - started, 3),
            "symbols": clean_symbols,
            "quarters_per_symbol": quarters_per_symbol,
            "themes": theme_map,
            "qveris": {
                "base_url": self.client.base_url,
                "session_id": self.session_id,
                "tools": {
                    "dates_tool_id": DATES_TOOL_ID,
                    "dates_tool_rank": discover["dates_tool_rank"],
                    "transcript_tool_id": TRANSCRIPT_TOOL_ID,
                    "transcript_tool_rank": discover["transcript_tool_rank"],
                },
                "date_execs": date_execs,
                "transcript_execs": transcript_execs,
            },
            "periods": [period.__dict__ for period in selected_periods],
            "missing_transcripts": missing,
            "analyses": analyses,
            "portfolio_view": portfolio_view,
            "research_brief": build_research_brief(analyses, portfolio_view),
        }


def _compact_execute_meta(execution: dict[str, Any]) -> dict[str, Any]:
    outcome = execution.get("execution_outcome")
    billing = execution.get("billing")
    return {
        "execution_id": execution.get("execution_id"),
        "success": execution.get("success"),
        "cost": execution.get("cost"),
        "billing_summary": billing.get("summary") if isinstance(billing, dict) else None,
        "outcome": outcome.get("outcome") if isinstance(outcome, dict) else None,
        "valid_result_count": outcome.get("valid_result_count") if isinstance(outcome, dict) else None,
    }


def build_portfolio_view(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    by_symbol: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"periods": 0, "themes": Counter(), "labels": Counter()}
    )
    theme_totals: Counter[str] = Counter()
    theme_labels: dict[str, Counter[str]] = defaultdict(Counter)
    timeline: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in analyses:
        symbol = str(row["symbol"])
        by_symbol[symbol]["periods"] += 1
        for theme, payload in (row.get("themes") or {}).items():
            count = int(payload.get("mentions") or 0)
            per_1k = float(payload.get("mentions_per_1k_words") or 0)
            labels = Counter(payload.get("labels") or {})
            by_symbol[symbol]["themes"][theme] += count
            by_symbol[symbol]["labels"].update(labels)
            theme_totals[theme] += count
            theme_labels[theme].update(labels)
            timeline[symbol].append(
                {
                    "period": row.get("period"),
                    "date": row.get("date"),
                    "theme": theme,
                    "mentions": count,
                    "mentions_per_1k_words": per_1k,
                    "labels": dict(labels),
                }
            )

    normalized = {
        symbol: {
            "periods": payload["periods"],
            "themes": dict(payload["themes"].most_common()),
            "labels": dict(payload["labels"]),
        }
        for symbol, payload in sorted(by_symbol.items())
    }
    leaders = {
        theme: max(
            normalized.items(),
            key=lambda item: int(item[1]["themes"].get(theme, 0)),
        )[0]
        for theme in theme_totals
        if normalized
    }
    momentum = build_theme_momentum(timeline)
    return {
        "theme_totals": dict(theme_totals.most_common()),
        "theme_labels": {theme: dict(labels) for theme, labels in theme_labels.items()},
        "by_symbol": normalized,
        "theme_leaders": leaders,
        "theme_momentum": momentum,
    }


def build_theme_momentum(timeline: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for symbol, rows in timeline.items():
        by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_theme[str(row["theme"])].append(row)
        for theme, theme_rows in by_theme.items():
            ordered = sorted(theme_rows, key=lambda item: str(item.get("date") or ""), reverse=True)
            if len(ordered) < 2:
                continue
            latest, previous = ordered[0], ordered[1]
            delta = round(
                float(latest.get("mentions_per_1k_words") or 0)
                - float(previous.get("mentions_per_1k_words") or 0),
                3,
            )
            out.append(
                {
                    "symbol": symbol,
                    "theme": theme,
                    "latest_period": latest.get("period"),
                    "previous_period": previous.get("period"),
                    "latest_per_1k": latest.get("mentions_per_1k_words"),
                    "previous_per_1k": previous.get("mentions_per_1k_words"),
                    "delta_per_1k": delta,
                }
            )
    return sorted(out, key=lambda item: abs(float(item["delta_per_1k"])), reverse=True)


def build_research_brief(
    analyses: list[dict[str, Any]],
    portfolio_view: dict[str, Any],
) -> dict[str, Any]:
    totals = portfolio_view.get("theme_totals") or {}
    labels = portfolio_view.get("theme_labels") or {}
    leaders = portfolio_view.get("theme_leaders") or {}
    momentum = portfolio_view.get("theme_momentum") or []

    top_themes = list(totals.keys())[:5]
    opportunity_themes = sorted(
        labels.items(),
        key=lambda item: int((item[1] or {}).get("opportunity") or 0),
        reverse=True,
    )[:3]
    risk_themes = sorted(
        labels.items(),
        key=lambda item: int((item[1] or {}).get("risk") or 0),
        reverse=True,
    )[:3]

    questions: list[str] = []
    for item in momentum[:5]:
        direction = "升温" if float(item["delta_per_1k"]) > 0 else "降温"
        questions.append(
            f"{item['symbol']} 的 {item['theme']} 主题在 {item['latest_period']} 相对 "
            f"{item['previous_period']} {direction}，需要回看管理层原话确认原因。"
        )
    for theme, counts in risk_themes:
        if int((counts or {}).get("risk") or 0) > 0:
            questions.append(
                f"{theme} 相关风险语境较多，建议检查这些表述是否来自管理层，还是分析师追问。"
            )

    return {
        "headline": _brief_headline(totals, leaders),
        "top_themes": top_themes,
        "opportunity_themes": [
            {"theme": theme, "count": int((counts or {}).get("opportunity") or 0)}
            for theme, counts in opportunity_themes
        ],
        "risk_themes": [
            {"theme": theme, "count": int((counts or {}).get("risk") or 0)}
            for theme, counts in risk_themes
        ],
        "diligence_questions": questions[:8],
        "coverage": {
            "transcripts": len(analyses),
            "symbols": sorted({str(row.get("symbol")) for row in analyses}),
        },
    }


def _brief_headline(totals: dict[str, Any], leaders: dict[str, Any]) -> str:
    if not totals:
        return "No transcript signals were extracted."
    top_theme, top_count = next(iter(totals.items()))
    leader = leaders.get(top_theme, "-")
    return f"{top_theme} is the strongest transcript theme ({top_count} mentions), led by {leader}."


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    symbols = ", ".join(report.get("symbols") or [])
    lines.append(f"# Earnings Call Signal Report: {symbols}")
    lines.append("")
    lines.append(
        f"Generated at `{report.get('generated_at')}` with QVeris search + execute. "
        f"Elapsed: `{report.get('elapsed_s')}s`."
    )
    lines.append("")

    brief = report.get("research_brief") or {}
    lines.append("## Research Brief")
    lines.append("")
    lines.append(f"- Headline: {brief.get('headline')}")
    lines.append(
        f"- Coverage: {brief.get('coverage', {}).get('transcripts')} transcripts, "
        f"{', '.join(brief.get('coverage', {}).get('symbols') or [])}"
    )
    if brief.get("diligence_questions"):
        lines.append("- Follow-up questions:")
        for question in brief["diligence_questions"]:
            lines.append(f"  - {question}")
    lines.append("")

    qveris = report.get("qveris") or {}
    tools = qveris.get("tools") or {}
    lines.append("## QVeris Tool Discovery")
    lines.append("")
    lines.append("| Tool | Tool ID | Search rank |")
    lines.append("|---|---|---:|")
    lines.append(
        f"| Transcript dates | `{tools.get('dates_tool_id')}` | {tools.get('dates_tool_rank')} |"
    )
    lines.append(
        f"| Transcript content | `{tools.get('transcript_tool_id')}` | {tools.get('transcript_tool_rank')} |"
    )
    lines.append("")

    lines.append("## Portfolio Theme View")
    lines.append("")
    lines.append("| Theme | Total mentions | Opportunity | Risk | Leading symbol |")
    lines.append("|---|---:|---:|---:|---|")
    portfolio = report.get("portfolio_view") or {}
    totals = portfolio.get("theme_totals") or {}
    leaders = portfolio.get("theme_leaders") or {}
    labels = portfolio.get("theme_labels") or {}
    for theme, count in totals.items():
        label_counts = labels.get(theme) or {}
        lines.append(
            f"| {theme} | {count} | {label_counts.get('opportunity', 0)} | "
            f"{label_counts.get('risk', 0)} | {leaders.get(theme, '-')} |"
        )
    lines.append("")

    lines.append("## Theme Momentum")
    lines.append("")
    lines.append("| Symbol | Theme | Latest | Previous | Latest / 1k words | Previous / 1k words | Delta |")
    lines.append("|---|---|---|---|---:|---:|---:|")
    for item in (portfolio.get("theme_momentum") or [])[:12]:
        lines.append(
            f"| {item['symbol']} | {item['theme']} | {item['latest_period']} | "
            f"{item['previous_period']} | {item['latest_per_1k']} | "
            f"{item['previous_per_1k']} | {item['delta_per_1k']} |"
        )
    lines.append("")

    lines.append("## Period Summaries")
    lines.append("")
    lines.append(
        "| Symbol | Period | Date | Words | Speakers | AI | Margin | China | Capex | Guidance |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in report.get("analyses") or []:
        themes = row.get("themes") or {}

        def mentions(name: str) -> int:
            return int((themes.get(name) or {}).get("mentions") or 0)

        lines.append(
            "| {symbol} | {period} | {date} | {words} | {speakers} | {ai} | {margin} | {china} | {capex} | {guidance} |".format(
                symbol=row.get("symbol"),
                period=row.get("period"),
                date=row.get("date"),
                words=row.get("word_count_estimate"),
                speakers=row.get("speaker_count"),
                ai=mentions("AI"),
                margin=mentions("Margin"),
                china=mentions("China"),
                capex=mentions("Capex"),
                guidance=mentions("Guidance"),
            )
        )
    lines.append("")

    lines.append("## Evidence Snippets")
    for row in report.get("analyses") or []:
        lines.append("")
        lines.append(f"### {row.get('symbol')} {row.get('period')}")
        for theme, payload in (row.get("themes") or {}).items():
            snippets = payload.get("snippets") or []
            if not snippets:
                continue
            lines.append("")
            lines.append(f"**{theme}**")
            for snippet in snippets[:2]:
                lines.append(
                    f"- [{snippet.get('label')}/{snippet.get('speaker_role')}] "
                    f"{snippet.get('speaker')}: {snippet.get('snippet')}"
                )
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- Each transcript/date retrieval is a real QVeris `execute` call and may consume credits.")
    lines.append("- The report is a research-assist artifact, not investment advice.")
    lines.append("- For external use, review source provider terms and add analyst judgment.")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "earnings_call_signal_report.json"
    markdown_path = output_dir / "earnings_call_signal_report.md"
    matrix_path = output_dir / "theme_matrix.csv"
    evidence_path = output_dir / "evidence_ledger.csv"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    _write_theme_matrix(report, matrix_path)
    _write_evidence_ledger(report, evidence_path)

    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "theme_matrix": str(matrix_path),
        "evidence_ledger": str(evidence_path),
    }


def _write_theme_matrix(report: dict[str, Any], path: Path) -> None:
    themes = list((report.get("themes") or {}).keys())
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "symbol",
                "period",
                "date",
                "words",
                "speakers",
                *themes,
                *[f"{theme}_per_1k_words" for theme in themes],
            ],
        )
        writer.writeheader()
        for row in report.get("analyses") or []:
            themes_payload = row.get("themes") or {}
            out = {
                "symbol": row.get("symbol"),
                "period": row.get("period"),
                "date": row.get("date"),
                "words": row.get("word_count_estimate"),
                "speakers": row.get("speaker_count"),
            }
            for theme in themes:
                payload = themes_payload.get(theme) or {}
                out[theme] = payload.get("mentions", 0)
                out[f"{theme}_per_1k_words"] = payload.get("mentions_per_1k_words", 0)
            writer.writerow(out)


def _write_evidence_ledger(report: dict[str, Any], path: Path) -> None:
    fieldnames = [
        "symbol",
        "period",
        "date",
        "theme",
        "term",
        "label",
        "speaker",
        "speaker_role",
        "snippet",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("analyses") or []:
            for evidence in row.get("evidence") or []:
                writer.writerow({field: evidence.get(field) for field in fieldnames})

