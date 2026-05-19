# QVeris Earnings Call Signal Demo

This demo turns earnings-call transcripts into a source-backed research brief.

It follows a practical analyst workflow:

1. Search QVeris for the right transcript tools.
2. Execute transcript-date and transcript-content tools.
3. Compare companies and quarters across investment themes.
4. Export a Markdown report, JSON payload, theme matrix CSV, and evidence ledger CSV.

The example is intentionally small, but the outputs are useful: analysts can inspect theme momentum, compare companies, and trace each signal back to transcript snippets.

## Setup

```bash
uv sync
cp .env.example .env
```

Fill `QVERIS_API_KEY` in `.env`.

## CLI

```bash
uv run earnings-signal \
  --symbols AAPL,NVDA,TSM \
  --quarters 2 \
  --themes AI,Margin,Guidance
```

Print the full Markdown report:

```bash
uv run earnings-signal \
  --symbols AAPL,NVDA \
  --quarters 2 \
  --markdown
```

Generated files:

- `outputs/earnings_call_signal_report.json`
- `outputs/earnings_call_signal_report.md`
- `outputs/theme_matrix.csv`
- `outputs/evidence_ledger.csv`

## API

```bash
uv run uvicorn earnings_call_signal.app:app --host 127.0.0.1 --port 8092
```

```bash
curl --noproxy '*' -s http://127.0.0.1:8092/health
curl --noproxy '*' -s http://127.0.0.1:8092/run \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["AAPL","NVDA"],"quarters":2,"themes":["AI","Margin","Guidance"]}'
```

## What makes the output useful

- `theme_matrix.csv` is ready for spreadsheet analysis.
- `evidence_ledger.csv` keeps the exact source snippets behind each signal.
- Theme momentum compares the latest quarter with the previous quarter per company.
- Risk/opportunity labels are simple lexical labels, not investment advice.

## Notes

The demo performs real QVeris `search` and `execute` calls, so it may consume API credits.

