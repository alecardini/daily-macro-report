# Daily Macro Report

A Python tool that generates a single self-contained HTML "morning brief" aggregating macro, markets, crypto, news and sentiment from free public sources — the cross-asset snapshot a trading desk reviews at the open.

## Overview

An active trader starts the day by manually checking a dozen dashboards: rates, equity futures, crypto flows, the economic calendar, overnight news. This tool automates that. One script pulls from roughly fifteen sources in parallel and renders a single static HTML page, produced fresh each morning in about a minute. The output is read-only and needs no server — you just open the file.

## Features

- **Overnight cross-asset recap** — moves since the prior US close (equity futures, 10Y yield, FX, commodities, crypto), with a one-line synthesis.
- **Economic calendar** — three-day high-impact events in local time, with released actuals for the key US prints (NFP, CPI/Core CPI, PCE, retail sales, jobless claims, Fed decision) pulled from FRED.
- **Rates & credit** — full Treasury curve, 2s10s / 3m10y spreads, real yield and breakeven, and HY/IG credit spreads shown as a percentile versus both full history and the current five-year regime.
- **Rate expectations** — the market-implied policy path from the Atlanta Fed's SOFR-options distribution (hold / hike / cut probabilities by quarter).
- **Crypto** — BTC/ETH/SOL prices and dominance, spot-ETF flows, and aggregated multi-exchange funding, open interest and 24h liquidations.
- **Liquidity & positioning** — stablecoin supply and net flow as a dry-powder proxy, plus Deribit put/call ratios and implied volatility (DVOL).
- **Equities** — US indices and pre-market futures, the Asian session, sector rotation, and an earnings calendar covering large caps and a crypto-proxy watchlist.
- **Sentiment** — crypto and equity Fear & Greed, the AAII survey, and VIX.
- **News** — breaking, central-bank, crypto, oil and AI feeds, de-duplicated and impact-ranked, each with a short, strictly descriptive LLM-generated summary.
- **Data-quality layer** — flags implausible or stale values (impossible prices, absurd moves, frozen sources) before rendering.
- *(Planned)* CFTC Commitment of Traders positioning.

## Data sources

All free or public-tier: FRED (Federal Reserve of St. Louis), the Atlanta Fed Market Probability Tracker, CoinGecko, Coinalyze, Deribit, DefiLlama, Binance, farside.co.uk, Forex Factory, Slickcharts, Yahoo Finance (with a Finnhub fallback), Frankfurter (ECB reference rates), Google Gemini (news synthesis), and RSS feeds from major financial and general-news outlets, the Fed / ECB / BoE / BoJ, and crypto publications.

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
