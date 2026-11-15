"""The stub Harsh starts from must run a full auction with zero violations."""
from src.bidders.stub_bidder import MyBidder
from src.engine import events as E
from src.engine import load_season, run_auction
from src.engine.bidder_api import POINTS, validate
from src.engine.bidders import ValuationBidder
from src.engine.synth import load_teams, make_pool


def test_stub_runs_a_full_2026_auction_with_zero_violations():
    rules = load_season(2026)
    teams = load_teams(rules)
    pool = make_pool(rules, 120, 5, sorted(teams))
    mine = sorted(teams)[0]
    bidders = {c: ValuationBidder(seed=i) for i, c in enumerate(sorted(teams))}
    bidders[mine] = MyBidder()
    res = run_auction(rules, pool, teams, bidders, seed=5)
    assert res.violations() == []
    assert len(res.lots) > 0 and res.log.of_type(E.SOLD)
    mine_decisions = [e for e in res.log.of_type(E.DECISION) if e.team == mine]
    assert mine_decisions and all(e.data["valid"] for e in mine_decisions)   # the stub never gives a bad answer
    assert all(e.team != mine for e in res.log.of_type(E.SOLD))               # it passes on every lot


def test_stub_answers_every_point():
    b = MyBidder()
    for p in POINTS:
        _, ok, why = validate(p, {"you": {}, "eligible_players": []}, b.decide({"point": p}))
        assert ok, (p, why)
