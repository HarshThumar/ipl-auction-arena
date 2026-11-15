"""Ollama client tests with a mocked HTTP layer (no network)."""
import pytest

from src.llm.ollama_client import OllamaClient, OllamaError, extract_json


def fake_post(reply='{"action": "stay_out"}'):
    sent = []

    def post(url, body, timeout):
        sent.append((url, body, timeout))
        return {"response": reply, "done": True}
    post.sent = sent
    return post


def test_extract_json_cases():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": {"b": 2}} hope it helps {"c": 3}') == {"a": {"b": 2}}
    assert extract_json('```json\n{"x": [1, 2]}\n```') == {"x": [1, 2]}
    assert extract_json('broken { not json } then {"ok": true}') == {"ok": True}
    assert extract_json("no json here") is None
    assert extract_json("[1, 2, 3]") is None
    assert extract_json("") is None


def test_request_shape_and_options(tmp_path):
    post = fake_post()
    c = OllamaClient("qwen2:7b", cache_dir=tmp_path, timeout=12, post=post)
    schema = {"type": "object"}
    r = c.generate_json("hello", schema=schema, seed=7, num_predict=50, system="be brief")
    url, body, timeout = post.sent[0]
    assert url == "http://localhost:11434/api/generate" and timeout == 12
    assert body["model"] == "qwen2:7b" and body["stream"] is False and body["format"] == schema
    assert body["options"] == {"temperature": 0.0, "num_predict": 50, "seed": 7} and body["system"] == "be brief"
    assert r.data == {"action": "stay_out"} and r.cached is False
    c.generate_json("hello2", seed=None)
    assert post.sent[1][1]["format"] == "json" and "seed" not in post.sent[1][1]["options"]


def test_cache_hit_gives_identical_answer_without_http(tmp_path):
    post = fake_post()
    c = OllamaClient(cache_dir=tmp_path, post=post)
    a = c.generate_json("p", seed=1)
    b = c.generate_json("p", seed=1)
    assert len(post.sent) == 1 and (c.calls, c.hits) == (1, 1)
    assert b.cached and not a.cached and a.text == b.text and a.key == b.key
    assert len(list(tmp_path.glob("*.json"))) == 1
    # a fresh client over the same folder also replays from disk
    c2 = OllamaClient(cache_dir=tmp_path, post=fake_post("different"))
    assert c2.generate_json("p", seed=1).text == a.text


def test_cache_key_depends_on_model_prompt_options(tmp_path):
    c = OllamaClient("m1", cache_dir=tmp_path, post=fake_post())
    k = c.generate_json("p", seed=1).key
    assert c.generate_json("p", seed=2).key != k
    assert c.generate_json("q", seed=1).key != k
    assert c.generate_json("p", seed=1, num_predict=10).key != k
    assert c.generate_json("p", seed=1, schema={"type": "object"}).key != k
    assert OllamaClient("m2", cache_dir=tmp_path, post=fake_post()).generate_json("p", seed=1).key != k


def test_errors_are_raised_and_not_cached(tmp_path):
    def boom(url, body, timeout):
        raise OllamaError("connection refused")
    c = OllamaClient(cache_dir=tmp_path, post=boom)
    with pytest.raises(OllamaError):
        c.generate_json("p")
    assert not list(tmp_path.glob("*.json"))
    bad = OllamaClient(cache_dir=tmp_path, post=lambda u, b, t: {"error": "model not found"})
    with pytest.raises(OllamaError):
        bad.generate_json("p")


def test_non_json_reply_gives_none_data_and_damaged_cache_is_ignored(tmp_path):
    c = OllamaClient(cache_dir=tmp_path, post=fake_post("I cannot decide"))
    r = c.generate_json("p")
    assert r.data is None and r.text == "I cannot decide"
    (tmp_path / f"{r.key}.json").write_text("{not json", encoding="utf-8")
    assert c.generate_json("p").cached is False


def test_no_cache_flag(tmp_path):
    post = fake_post()
    c = OllamaClient(cache_dir=tmp_path, post=post)
    c.generate_json("p", use_cache=False)
    c.generate_json("p", use_cache=False)
    assert len(post.sent) == 2 and not list(tmp_path.glob("*.json"))
