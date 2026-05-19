from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .analyzer import DEFAULT_THEMES, EarningsCallSignalAnalyzer, select_themes, render_markdown, write_outputs

app = FastAPI(title="QVeris Earnings Call Signal Demo")


class AnalyzeRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "NVDA", "TSM"])
    quarters: int = Field(default=2, ge=1, le=8)
    theme_set: str = "extended"
    themes: list[str] | None = None
    market_context: bool = False
    write_files: bool = True


def _theme_subset(names: list[str] | None, theme_set: str) -> dict[str, list[str]]:
    if not names:
        return select_themes(None, theme_set=theme_set)
    selected = select_themes(names, theme_set=theme_set)
    return selected or DEFAULT_THEMES


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
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
          <p>Search QVeris for earnings-call transcript tools, execute them, and turn long transcripts into a source-backed research brief with theme momentum, evidence ledgers, and optional market context.</p>
          <div class="panel">
            <p>Try <code>POST /run</code> with JSON: <code>{"symbols":["AAPL","NVDA"],"quarters":2,"theme_set":"extended","market_context":true}</code></p>
            <p>Try <code>POST /run/markdown</code> for a Markdown report.</p>
          </div>
        </main>
      </body>
    </html>
    """


@app.post("/run")
async def run(req: AnalyzeRequest) -> dict[str, object]:
    report = await EarningsCallSignalAnalyzer().run(
        symbols=req.symbols,
        quarters_per_symbol=req.quarters,
        themes=_theme_subset(req.themes, req.theme_set),
        include_market_context=req.market_context,
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
        include_market_context=req.market_context,
    )
    if req.write_files:
        write_outputs(report, Path("outputs"))
    return render_markdown(report)
