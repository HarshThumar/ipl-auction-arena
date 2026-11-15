"""L1 gate: the engine replays the real 2022-2026 auctions from the recorded outcomes with zero rule
violations (docs/replay-report.md). Committed data only."""
import pytest

from src.engine.replay import OFFICIAL, SEASONS, replay_season


@pytest.fixture(scope="module")
def reports():
    return {y: replay_season(y) for y in SEASONS}


@pytest.mark.parametrize("season", SEASONS)
def test_zero_problems(reports, season):
    assert reports[season].problems == []


@pytest.mark.parametrize("season", SEASONS)
def test_exact_outcomes_and_official_totals(reports, season):
    r = reports[season]
    assert r.outcomes_exact == r.lots
    assert (r.sold, r.hammer_total_lakh) == OFFICIAL[season]


@pytest.mark.parametrize("season", SEASONS)
def test_squads_and_overseas_at_the_end(reports, season):
    r = reports[season]
    assert 18 <= r.min_squad and r.max_squad <= 25
    assert r.max_overseas <= 8


def test_official_totals_match_the_published_figures():
    crore = {y: v[1] / 100 for y, v in OFFICIAL.items()}
    assert crore == {2022: 551.7, 2023: 167.0, 2024: 230.45, 2025: 639.15, 2026: 215.45}
    assert {y: v[0] for y, v in OFFICIAL.items()} == {2022: 204, 2023: 80, 2024: 72, 2025: 182, 2026: 77}


def test_cameron_green_2026_paid_1800_charged_2520(reports):
    assert any("Cameron Green" in n and "2520" in n and "1800" in n for n in reports[2026].notes)


def test_replay_is_deterministic(reports):
    assert replay_season(2023).log_digest == reports[2023].log_digest
