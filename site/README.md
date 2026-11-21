# Site (L7)

Static Astro site for the IPL Auction Arena: home, franchise pages, forecast, scorecard, hash & pre-registration. Not official, not affiliated; no logos, no betting angle (see the footer on every page).

## Build

```powershell
cd site
npm install
npm run build      # output in site/dist
npm run dev        # local preview with reload
```

Hosting is any static host ($0): GitHub Pages or Cloudflare Pages. For a GitHub Pages project site build with `SITE_BASE=/<repo-name>` (and optionally `SITE_URL`). Nothing is deployed from here.

## Where the data comes from (read at build time)

| Page | Source |
|---|---|
| Franchises | `../data/reference/franchises.csv` (owner and source URL columns are not published) |
| Scorecard | `../data/processed/l2/l2_scores.json` (base price, LightGBM decisions), `auctioniq_scores.json`, `llm_scores.json` |
| Forecast, franchise "likely targets" | `site/data/forecast.json` if present (gitignored until freeze), else `site/data/forecast.sample.json` (FAKE) |
| Hash | `site/data/hash.json` if present, else an all-zero placeholder |

The "Our model" scorecard column reads "not yet" until the model is trained and scored; the pundit mock is scored only on the live auction. Fonts (Newsreader, IBM Plex Sans, IBM Plex Mono; SIL Open Font Licence) are self-hosted through `@fontsource`, so the site makes no third-party requests.

## Forecast JSON schema

Full JSON Schema: `data/forecast.schema.json`. Shape:

```json
{
  "schema_version": 1,
  "status": "FAKE_SAMPLE | FROZEN",
  "auction_date": "2026-12-16",
  "frozen_at": "ISO time or null",
  "model": "label",
  "n_seeds": 20,
  "currency": "INR lakh",
  "players": [{
    "player_id": "string", "name": "string", "role": "string",
    "base_price_lakh": 200,
    "p_sold": 0.93,
    "buyer_distribution": { "MI": 0.3, "RCB": 0.25 },
    "price_interval_lakh": { "p10": 220, "p50": 420, "p90": 780 }
  }]
}
```

`buyer_distribution` is conditional on sold (keys are `franchise_id`, values sum to about 1). `price_interval_lakh` is conditional on sold. Any `status` other than `FROZEN` shows a warning "FAKE SAMPLE DATA" banner.

## Hash JSON (`data/hash.json`)

```json
{ "status": "FROZEN", "sha256": "<64 hex>", "file": "forecast.json", "frozen_at": "ISO time", "doi": "10.xxxx/..." }
```

Generate with `Get-FileHash forecast.json -Algorithm SHA256`. Hash the exact bytes you archive.

## Notes

- Team colours are an accent stripe only; no logos.
- The 2018–21 bid-trail source is intentionally not named anywhere.
- Backtest scores are shown with their caveats; baselines win some rows and that is left visible.
