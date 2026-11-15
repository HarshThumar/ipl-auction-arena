from src.engine import events as E
from src.engine import load_season, run_auction, voice
from src.engine.board import crore, render_board
from src.engine.synth import load_teams, make_bidders, make_pool


def run(seed=2):
    rules = load_season(2025)
    teams = load_teams(rules)
    pool = make_pool(rules, 40, seed, sorted(teams))
    return run_auction(rules, pool, teams, make_bidders("valuation", sorted(teams), seed), seed=seed)


def test_crore_formatting():
    assert crore(0) == "0.00" and crore(5) == "0.05" and crore(100) == "1.00"
    assert crore(4340) == "43.40" and crore(1225) == "12.25" and crore(-30) == "-0.30"


def test_board_has_every_team_and_matches_state():
    res = run()
    text = render_board(res.room)
    lines = text.splitlines()
    assert len(lines) == 2 + len(res.room.teams)
    for code, t in res.room.teams.items():
        row = next(ln for ln in lines if ln.startswith(code))
        assert crore(t.purse_lakh) in row and str(t.squad) in row
    assert render_board(res.room) == text


def test_board_shows_at_most_five_recent_lots():
    res = run()
    for line in render_board(res.room).splitlines()[2:]:
        assert line.count(";") <= 4


def test_voice_is_deterministic_and_generic():
    a = voice.line("sold", 1, "lot1", player="Player 001", team="MI", price=250)
    assert a == voice.line("sold", 1, "lot1", player="Player 001", team="MI", price=250)
    assert "2.50" in a and "MI" in a
    for kind in voice.TEMPLATES:
        s = voice.line(kind, 3, "x", player="P", team="MI", teams=["MI", "CSK"], price=100, base=20)
        assert s and "{" not in s
    text = " ".join(t for ts in voice.TEMPLATES.values() for t in ts).lower()
    for banned in ("ipl", "bcci", "hugh", "charu", "mallika"):
        assert banned not in text


def test_narrate_covers_a_run_and_is_deterministic():
    res = run()
    n1 = voice.narrate(res.log.events, seed=4)
    assert n1 == voice.narrate(res.log.events, seed=4)
    assert len(n1) >= len(res.log.of_type(E.SOLD))
    assert any("going once" in s for s in n1)
