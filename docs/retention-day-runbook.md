# Retention day runbook (17 Nov 2026)

What we need from retention day: for each of the 10 teams, **who they kept, purse left, slots left and overseas slots left**. Everything in the forecast starts from these numbers.

The same code has been backtested on 2022–2026. It matches the published slot and overseas-slot counts exactly for every team in 2023, 2024 and 2026, and the published purse totals too (`python scripts/build_pre_auction_state.py --backtest`).

## Steps

1. **Official figures first.** When the official purse and slots table comes out (iplt20.com press release, ESPNcricinfo or Wisden all print it the same evening), add 10 rows to [data/reference/pre_auction_official.csv](../data/reference/pre_auction_official.csv):
   `2027,<TEAM>,<purse left in lakh>,<slots left>,<overseas slots left>,<URL>`
   - Read iplt20.com only to check. Never scrape it. Cite ESPNcricinfo or Wisden.
   - The column totals should match the headline totals in the article (e.g. "77 slots, 31 overseas").
2. **Retained players.** Use either source:
   - Wikipedia, once its "Player retention" tables are filled: `python -I scripts/parse_retentions.py --fetch 2027`
   - A hand-typed CSV in `data/raw/retentions/2027_retained.csv` with columns `team,player,nationality,salary_lakh,source`. Nationality is `India` or `Overseas` and salary is in lakh. [tests/fixtures/mock_2027_retained.csv](../tests/fixtures/mock_2027_retained.csv) shows the format.
3. **Build the state:**
   `python scripts/build_pre_auction_state.py --season 2027` (Wikipedia), or add `--retained-csv data/raw/retentions/2027_retained.csv`
   - Exit code 1 means a hard check failed. Fix the input and don't hand-edit the output.
   - `FINAL` means the official figures are present for all 10 teams. `PROVISIONAL` means they aren't yet.
4. **Gate:** run `python scripts/validate_l0.py`, which needs "2027 retentions loaded" to PASS, then `python -m pytest -q`. Then tick L0.

## What each check catches

| Check | Failure it catches | Seen for real in the backtest |
|---|---|---|
| Slots left = official | A player missing from or extra in the list | 2024: unlinked wiki names were dropped (DC, PBKS, RCB) |
| Overseas slots = official | Wrong nationality, or a missing overseas player | |
| Salary ≥ 20 lakh | Unit typo (lakh instead of crore) | 2024: Padikkal listed as "7.75 lakh" |
| No player on two teams | Table boundary bug, or a trade counted twice | 2026: each team's last player was filed under the next team |
| All 10 teams present | A missing table | |
| Purse: derived vs official | Shown as a WARN, because the official figure wins | Retention-slab charge, see below |

## Why derived purse ≠ official purse (and why that is OK)

Derived purse is the season purse minus the retained salaries. It differs from the official figure for a few teams because:

- At a mega auction, a retained player costs the team its **retention slab** even when he signs for less (2025: KKR kept Rinku Singh at 13 cr against an 18 cr slab).
- That charge **stays on the purse for the whole cycle**. 2026 KKR's gap was 6 cr. In the last cycle, the DC (3.5 cr) and KKR (8 cr) gaps were identical in 2022 and 2023.

2027 is the last mini auction of the 2025–27 cycle, so expect the same gaps for teams that kept their 2025 retentions. The official figure is always used. If you want a hint, the script prints last season's gap per team when official figures are missing.

## Before 17 Nov

- Dry run: `python scripts/build_pre_auction_state.py --season 2027 --retained-csv tests/fixtures/mock_2027_retained.csv`. It should print PROVISIONAL with exit code 0. Delete `data/processed/pre_auction_state/2027.json` afterwards.
- The 2027 purse of 130 cr is still unconfirmed in [rules_by_season.yaml](../data/reference/rules_by_season.yaml). It only feeds the derived cross-check, and the official per-team figures replace it.
