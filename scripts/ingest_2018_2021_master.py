"""Data pipeline to ingest, normalize, and merge 2018-2021 lots into master dataset."""

import json
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = REPO_ROOT / "data" / "raw" / "enrichment_recon" / "gh_kalilur_auction.csv"
FRANCHISES_FILE = REPO_ROOT / "data" / "reference" / "franchises.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "2018_2021_staging"


def get_franchise_code_map() -> dict:
    df_f = pd.read_csv(FRANCHISES_FILE)
    name_to_code = {}
    for _, row in df_f.iterrows():
        code = row["franchise_id"]
        name_to_code[row["current_name"].strip().lower()] = code
        if pd.notna(row["aliases"]):
            for alias in str(row["aliases"]).split(";"):
                name_to_code[alias.strip().lower()] = code
    return name_to_code


def normalize_team(raw_team: str, code_map: dict) -> str:
    cleaned = str(raw_team).strip().lower()
    if cleaned in code_map:
        return code_map[cleaned]
    # Specific overrides
    if "delhi" in cleaned:
        return "DC"
    if "punjab" in cleaned:
        return "PBKS"
    if "bangalore" in cleaned or "bengaluru" in cleaned:
        return "RCB"
    if "hyderabad" in cleaned:
        return "SRH"
    if "kolkata" in cleaned:
        return "KKR"
    if "mumbai" in cleaned:
        return "MI"
    if "chennai" in cleaned:
        return "CSK"
    if "rajasthan" in cleaned:
        return "RR"
    return "UNKNOWN"


def ingest_2018_2021():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df_raw = pd.read_csv(RAW_FILE)
    df_target = df_raw[df_raw["Year"].isin([2018, 2019, 2020, 2021])].copy()
    code_map = get_franchise_code_map()

    normalized_rows = []
    for _, row in df_target.iterrows():
        season = int(row["Year"])
        player_name = str(row["Player"]).strip()
        role = str(row["Role"]).strip().lower()
        is_overseas = str(row.get("Player Origin", "")).strip().lower() == "overseas"
        amount_raw = int(row["Amount"])
        price_lakh = amount_raw // 100_000
        team_code = normalize_team(row["Team"], code_map)

        normalized_rows.append({
            "season": season,
            "player_name": player_name,
            "role": role,
            "is_overseas": is_overseas,
            "hammer_price_lakh": price_lakh,
            "paid_price_lakh": price_lakh,
            "winner_team_code": team_code,
            "status": "sold",
        })

    df_out = pd.DataFrame(normalized_rows)
    out_file = OUTPUT_DIR / "staged_2018_2021.csv"
    df_out.to_csv(out_file, index=False)
    print(f"Successfully staged {len(df_out)} lots across 2018-2021 into {out_file}")
    print(df_out["season"].value_counts().sort_index())
    print("\nTeam distribution:")
    print(df_out["winner_team_code"].value_counts())


if __name__ == "__main__":
    ingest_2018_2021()
