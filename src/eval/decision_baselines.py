"""Decision-level baselines (L2): predict P(DROP) for each {state -> RAISE/DROP} row.

This is the bar the shared LoRA + identity embedding has to beat at L3, scored on the same rows.

As-of rule (register D2/C5): FORWARD-CHAINING only. To score season s we train on seasons < s.
splits.json also offers leave-one-season-out folds, but those train on future auctions to predict
past ones, which a real forecaster can't do, so they are not used for the reported L2 numbers.

Fixed config, no tuning on the scored seasons (register D5). Any change to PARAMS or FEATURES
is a new config and must be logged in the report.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CATEGORICAL = ["franchise_id", "era", "role", "rival_id"]
IDENTITY = ["franchise_id", "rival_id"]
NUMERIC = [
    "is_overseas", "capped", "base_price_lakhs", "set_no", "step_index",
    "current_price_lakhs", "next_increment_lakhs", "lots_done", "spend_so_far_lakhs",
    "spend_pace_vs_expected", "purse_left_lakhs", "slots_left", "overseas_left", "role_gap",
    "is_final_two", "rival_purse_left_lakhs", "rival_slots_left", "rival_role_gap",
    "n_active_estimate", "same_role_remaining", "same_role_avg_base",
]
DERIVED = ["price_over_base", "price_share_of_purse", "purse_minus_rival_purse"]
FEATURES = CATEGORICAL + NUMERIC + DERIVED

# Never model inputs. `contested` and `confidence` describe the whole lot, known only after it ends.
FORBIDDEN = {
    "action", "season", "lot_id", "player", "contested", "confidence",
    "final_price", "winner", "final_two", "hammer_lakh", "paid_lakh",
}

PARAMS = dict(
    objective="binary", learning_rate=0.05, n_estimators=300, num_leaves=7,
    min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
    reg_lambda=1.0, random_state=0, deterministic=True, force_row_wise=True, verbose=-1,
)
TEAM_PRIOR_STRENGTH = 20.0


def label(df: pd.DataFrame) -> np.ndarray:
    return (df["action"] == "DROP").astype(int).to_numpy()


def war_mask(df: pd.DataFrame) -> np.ndarray:
    """Rows inside a real bidding war: contested lot, after the opening bid.

    Used only to pick an evaluation subset, never as a feature.
    """
    return (df["contested"].astype(bool) & (df["step_index"] >= 1)).to_numpy()


def forward_split(df: pd.DataFrame, val_season: int):
    train = df[df["season"] < val_season]
    val = df[df["season"] == val_season]
    return train, val


def make_X(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    assert not (set(features) & FORBIDDEN), "forbidden column in features"
    X = df.copy()
    X["price_over_base"] = X["current_price_lakhs"] / X["base_price_lakhs"].clip(lower=1)
    X["price_share_of_purse"] = X["current_price_lakhs"] / X["purse_left_lakhs"].clip(lower=1)
    X["purse_minus_rival_purse"] = X["purse_left_lakhs"] - X["rival_purse_left_lakhs"]
    X = X[features].copy()
    for c in features:
        if c in CATEGORICAL:
            X[c] = X[c].astype("string").fillna("NONE").astype("category")
        else:
            X[c] = pd.to_numeric(X[c], errors="coerce").astype(float)
    return X


class Prior:
    name = "prior"

    def fit(self, train):
        self.p = float(label(train).mean())
        return self

    def predict(self, df):
        return np.full(len(df), self.p)


class TeamPrior:
    """Each franchise's own DROP rate, shrunk toward the league rate."""

    name = "team_prior"

    def fit(self, train):
        y = label(train)
        self.p0 = float(y.mean())
        g = pd.DataFrame({"t": train["franchise_id"].to_numpy(), "y": y}).groupby("t")["y"]
        self.rate = ((g.sum() + TEAM_PRIOR_STRENGTH * self.p0) / (g.count() + TEAM_PRIOR_STRENGTH)).to_dict()
        return self

    def predict(self, df):
        return df["franchise_id"].map(self.rate).fillna(self.p0).to_numpy(float)


class LGBM:
    def __init__(self, with_identity: bool = True):
        self.features = FEATURES if with_identity else [f for f in FEATURES if f not in IDENTITY]
        self.name = "lightgbm" if with_identity else "lightgbm_no_identity"

    def fit(self, train):
        import lightgbm as lgb

        X = make_X(train, self.features)
        self.categories = {c: X[c].cat.categories for c in X.columns if c in CATEGORICAL}
        self.model = lgb.LGBMClassifier(**PARAMS).fit(X, label(train))
        return self

    def predict(self, df):
        X = make_X(df, self.features)
        for c, cats in self.categories.items():
            v = X[c].astype("string")
            X[c] = pd.Categorical(v.where(v.isin(cats)), categories=cats)  # unseen -> missing
        return self.model.predict_proba(X)[:, 1]


def all_models():
    return [Prior(), TeamPrior(), LGBM(True), LGBM(False)]
