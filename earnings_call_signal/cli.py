from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from .analyzer import DEFAULT_THEMES, EarningsCallSignalAnalyzer, render_markdown, write_outputs

app = typer.Typer(add_completion=False, help="Analyze earnings call transcript signals with QVeris.")


def _parse_symbols(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _theme_subset(value: str | None) -> dict[str, list[str]]:
    if not value:
        return DEFAULT_THEMES
    requested = {item.strip() for item in value.split(",") if item.strip()}
    selected = {name: terms for name, terms in DEFAULT_THEMES.items() if name in requested}
    if not selected:
        raise typer.BadParameter(f"No known themes in {value!r}. Known: {', '.join(DEFAULT_THEMES)}")
    return selected


@app.callback(invoke_without_command=True)
def run(
    symbols: str = typer.Option("AAPL,NVDA,TSM", help="Comma-separated stock symbols."),
    quarters: int = typer.Option(2, min=1, max=8, help="Recent quarters per symbol."),
    themes: str | None = typer.Option(None, help="Optional theme subset, e.g. AI,Margin,Guidance."),
    output_dir: Path = typer.Option(Path("outputs"), help="Directory for JSON, Markdown, and CSV outputs."),
    markdown: bool = typer.Option(False, help="Print Markdown instead of JSON summary."),
    write_files: bool = typer.Option(True, help="Write report files to output_dir."),
) -> None:
    report = asyncio.run(
        EarningsCallSignalAnalyzer().run(
            symbols=_parse_symbols(symbols),
            quarters_per_symbol=quarters,
            themes=_theme_subset(themes),
        )
    )
    paths: dict[str, str] = {}
    if write_files:
        paths = write_outputs(report, output_dir)
    if markdown:
        typer.echo(render_markdown(report))
    else:
        typer.echo(
            json.dumps(
                {
                    "generated_at": report["generated_at"],
                    "elapsed_s": report["elapsed_s"],
                    "symbols": report["symbols"],
                    "periods": report["periods"],
                    "research_brief": report["research_brief"],
                    "portfolio_view": report["portfolio_view"],
                    "outputs": paths,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    app()

