# investor-finder

Finds small US venture funds that lean consumer / B2C (with a marketplace tilt
where possible), and resolves a LinkedIn URL and a best-effort email for each
fund's founders and partners. Built to assemble a targeted outreach list of
100 to 200 funds in a single run.

Built to source a pre-seed round; open-sourced because the pipeline
(LLM-proposed candidates verified against the live web, fund sizes pulled from
SEC Form D, contacts resolved with confidence tags) generalizes to any founder
doing the same legwork. Tune the seed list and filters for your own thesis.

## What it produces

A founder-level CSV: one row per partner, with the fund's thesis, sectors,
stage, check size, an estimated fund size with a confidence flag, whether it is
sub-$20M, whether it is consumer and whether it is a marketplace specialist,
plus the partner's role, LinkedIn URL, and email. Every contact is tagged with
how it was found and how much to trust it, so high-confidence rows and guesses
are never confused.

It can also push the same table to Notion.

## How it works

1. **Discover** a large candidate pool from three independent sources: a curated
   seed list, an LLM proposing real funds across many angles, and Google
   "best consumer VC funds" style article harvesting. Recall over precision
   here on purpose.
2. **Verify and profile** every candidate against the live web (its own site
   plus search evidence). An LLM returns one structured record per firm and
   decides whether it is a real US venture fund. Anything it cannot verify, or
   that is not US-based, is dropped, so no hallucinated fund reaches the list.
3. **Filter** to consumer or marketplace funds, US only, at or under the fund
   size ceiling.
4. **Resolve contacts**: a LinkedIn URL and a best-effort email per partner,
   each with a source and confidence.
5. **Output** the CSV and optionally a Notion table.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # fill in the keys you have
```

The tool needs a Google search key (Serper or Piloterr) and an LLM key (OpenAI
or xAI/Grok) at minimum. Coresignal and EnrichLayer are optional enrichment
boosters. When run next to a sibling `thescraper/` checkout it reads any missing
keys from `../thescraper/.env` automatically.

## Run

```
python run.py                       # full run, default target
python run.py --target 200          # aim for ~200 funds
python run.py --max-candidates 500  # widen the discovery pool
python run.py --no-listicles        # skip article harvesting (faster)
python run.py --enrichment-email    # also try the paid email endpoint
python run.py --out data/funds.csv  # output path
python run.py --notion              # also push to Notion (needs token + parent)
```

## Notes on data quality

- **Fund size** is the one figure nobody publishes cleanly for micro funds. It
  is an estimate from team size, fund vintage, check size, and any public
  number, with a `size_confidence` flag. Treat low confidence as a hint.
- **Email** is best-effort. Order of preference: published on the firm site
  (high) > derived from the firm's observed address pattern (medium) >
  enrichment API (medium) > a single pattern guess (low). The `email_source`
  and `email_confidence` columns tell you which.
- **LinkedIn** is taken from the site when visible, otherwise resolved by
  search. Run with `--enrichment-email` plus the EnrichLayer key to also verify
  profiles.

## Outreach angles (optional)

`python fit.py` drafts a one-line "why this fund fits" and a cold-open hook per
fund, grounded in each fund's stated thesis. Set `COMPANY_NAME` and
`COMPANY_PITCH` in your `.env` so the drafts are about your company; with no
pitch set it falls back to a placeholder. These are starting drafts, meant to be
edited before you send anything.

## Layout

```
config.py            secret loading (.env + sibling fallback)
providers/           thin API clients: search, web, llm, people, http
pipeline/            discover -> profile -> classify -> contacts -> output
  seeds.py           curated seed funds
run.py               orchestrator / CLI
fit.py               optional per-fund outreach angle drafts
```
