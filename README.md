# Daily Macro Report

A Python tool that generates a single self-contained HTML "morning brief" aggregating macro, markets, crypto, news and sentiment from free public sources — the cross-asset snapshot a trading desk reviews at the open.

## Overview

An active trader starts the day by manually checking a dozen dashboards: rates, equity futures, crypto flows, the economic calendar, overnight news. This tool automates that. One script pulls from roughly fifteen sources in parallel and renders a single static HTML page, produced fresh each morning in a few minutes. The output is read-only and needs no server — you just open the file.

## Features

- **Overnight cross-asset recap** — moves since the prior US close (equity futures, 2Y and 10Y yields via Treasury futures, FX including DXY, commodities, crypto), with a one-line synthesis.
- **Economic calendar** — three-day high-impact events in Rome time (DST-aware), with released actuals for every currency, revisions to the previous print, "tentative" flags when a release time isn't confirmed, and market holidays / early closes (including US bank-only holidays when stocks still trade).
- **Rates & credit** — full Treasury curve, 2s10s / 3m10y spreads, real yield and breakeven, and HY/IG credit spreads shown as a percentile versus both full history and the current five-year regime.
- **Rate expectations** — per-meeting hold / hike / cut probabilities for the next four FOMC meetings, derived from 30-day Fed Funds futures (ZQ) with the CME FedWatch methodology.
- **Crypto** — BTC/ETH/SOL prices and dominance, spot-ETF flows, and aggregated multi-exchange funding, open interest and 24h liquidations.
- **Liquidity & positioning** — stablecoin supply and 7/30/90-day net flows as a dry-powder proxy, each ranked as a percentile versus both full history and the last three years, plus Deribit put/call ratios and implied volatility (DVOL).
- **Equities** — US indices and pre-market futures, the Asian session, sector rotation, and an earnings calendar covering large caps and a crypto-proxy watchlist.
- **Sentiment** — crypto and equity Fear & Greed, the AAII survey, and VIX.
- **News** — breaking, central-bank, crypto, oil and AI feeds, de-duplicated and impact-ranked, each with a short, strictly descriptive LLM-generated summary.
- **Data-quality layer** — flags implausible or stale values (impossible prices, absurd moves, frozen sources) before rendering.

## Data sources

All free or public-tier: FRED (Federal Reserve of St. Louis), CME Fed Funds futures (via Yahoo Finance), CoinGecko, Coinalyze, Deribit, DefiLlama, Binance, SoSoValue (ETF flows, with farside.co.uk as fallback), Forex Factory, Slickcharts, Yahoo Finance (with a Finnhub fallback), Google Gemini (news synthesis), and RSS feeds from major financial and general-news outlets, the Fed / ECB / BoE / BoJ, and crypto publications.

## Tech stack

Python 3 — `requests`, `feedparser`, `BeautifulSoup`, `yfinance`, `pandas`, `pytz`, `openpyxl`. The output is a single static HTML file: no framework, no server, no database.

## How it works

1. **Collect** — the sources are fetched in parallel, each call isolated so a single failure can't break the run. Fragile sources have a different-provider fallback and short-lived caching.
2. **Process** — normalize and de-duplicate news, rank it by market impact, run plausibility checks on the data, compute derived metrics (curve spreads, percentiles, implied rates), and generate the news summaries with a single, tightly-constrained LLM call.
3. **Render** — assemble a themed, self-contained HTML report and open it in the browser.

## Running it

```bash
pip install -r requirements.txt
python3 generate_report.py
```

API keys are read from a local, git-ignored configuration file (a template is provided) and are never committed to the repository.

## Notes

A personal project, built for my own daily use rather than as production software. Development was AI-assisted.
