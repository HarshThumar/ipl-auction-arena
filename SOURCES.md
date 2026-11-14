# Data sources & licences

This dataset was assembled from public, openly-licensed sources. Attribution is
required by those licences and is provided here.

| Layer | Source | Licence |
|---|---|---|
| Auction outcomes & player enrichment (role, nationality, capped status, base/final price, team) | Wikipedia — "List of 20XX Indian Premier League personnel changes" | CC BY-SA 4.0 |
| Player identifiers (cricsheet / cricinfo IDs) | Cricsheet Register (people.csv) | ODC-BY 1.0 |
| Player roles from match data (batting position, overs by phase, stumpings) | Cricsheet ball-by-ball T20 data, https://cricsheet.org | ODC-BY 1.0 |
| Player performance numbers before each auction (runs, strike rate, wickets, economy, by phase; `data/processed/player_features/`) | Cricsheet ball-by-ball T20 data, men's T20/IT20 from 2014 | ODC-BY 1.0 |
| Bowling style, batting hand, career role | Wikipedia "Infobox cricketer", found via Wikidata property P2697 | CC BY-SA 4.0 (Wikipedia), CC0 (Wikidata) |
| Retentions, pre-auction trades | Wikipedia season articles ("Retained players", "Transfers") | CC BY-SA 4.0 |
| Date of birth | Wikidata property P569, matched by ESPNcricinfo ID (P2697) | CC0 |
| International caps (Tests, ODIs, T20Is) for capped/uncapped status | Cricsheet full-history international archives | ODC-BY 1.0 |
| Auction set structure and the 2024 set-wise list | News reports, one URL per season in `data/reference/auction_set_structure.yaml` | facts, cited |
| Official pre-auction purse and slots | News reports, one URL per row in `data/reference/pre_auction_official.csv` | facts, cited |
| Bid sequences (opener → raises → final two) | Reconstructed **facts** from publicly archived match commentary | facts not subject to copyright |

Notes:
- Content derived from the Wikipedia tables is itself made available under **CC BY-SA 4.0**.
- Cricsheet attribution is required under **ODC-BY**; see https://cricsheet.org .
- Bid sequences record only factual events (who bid, how much, who won). No
  third-party prose, images, logos, audio or video are reproduced.
- Figures are cross-checked against official auction totals; small residual
  disagreements with official spend are documented in the dataset's validation output.
