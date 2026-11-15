"""A tiny client for a local Ollama server (POST /api/generate), with an exact-replay disk cache.

Why a cache: even at temperature 0, Ollama does not promise the same text twice. Every call is
stored on disk under runs/llm_cache/<sha256>.json, keyed by sha256 of (model, prompt, options).
A replay reads the cache and gets the identical answer. runs/ is gitignored.

Rules (project): only local Ollama for anything validated. The free Gemini tier is allowed only as a
live-forecast fallback and never for backtests; it is not in this module. The model never does
arithmetic: the engine passes ready-made numbers in the prompt.

Measured speed on the dev laptop (i7-1355U, no GPU, 16 GB RAM, qwen2:7b on CPU): one 1,660-token
call takes 170 s cold and 9 s when the prompt prefix is already cached by Ollama. That is far too
slow for 20+ seeds of a full auction (about 1,200 calls per seed). The big runs therefore go to a
free cloud GPU notebook (Kaggle or Colab) running Ollama; the laptop is for development only. Point
`host` at that Ollama server (for example through a tunnel) to use it.

Usage:
    client = OllamaClient(model="qwen2:7b")
    out = client.generate_json(prompt, schema=SCHEMAS["enter"], seed=1, num_predict=200)
    out.data      # the parsed dict, or None if the model returned no JSON object
    out.cached    # True when it came from the disk cache
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / "runs" / "llm_cache"


class OllamaError(RuntimeError):
    """The server could not be reached or answered with an error (never cached)."""


@dataclass
class LLMResult:
    text: str
    data: Optional[Dict[str, Any]]
    cached: bool
    key: str


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """The first JSON object found in `text` (models often wrap JSON in prose or code fences)."""
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text, i)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        i = text.find("{", i + 1)
    return None


def _http_post(url: str, body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise OllamaError(f"{type(exc).__name__}: {exc}") from exc


class OllamaClient:
    def __init__(self, model: Optional[str] = None, host: Optional[str] = None,
                 cache_dir: Optional[Path] = None, timeout: float = 300.0,
                 post: Optional[Callable[[str, Dict[str, Any], float], Dict[str, Any]]] = None):
        # model and host default to the OLLAMA_MODEL / OLLAMA_HOST environment variables, so the same
        # code runs on the laptop and on the cloud GPU notebook (docs/kaggle-gpu.md)
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2:7b")
        host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        if not host.startswith("http"):
            host = "http://" + host
        self.url = host.rstrip("/") + "/api/generate"
        self.cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE
        self.timeout = timeout
        self._post = post or _http_post
        self.calls = 0          # real HTTP calls made
        self.hits = 0           # answers served from the cache

    def options(self, seed: Optional[int], num_predict: int, temperature: float = 0.0) -> Dict[str, Any]:
        o: Dict[str, Any] = {"temperature": temperature, "num_predict": num_predict}
        if seed is not None:
            o["seed"] = seed
        return o

    def cache_key(self, prompt: str, options: Dict[str, Any], fmt: Any) -> str:
        blob = json.dumps({"model": self.model, "prompt": prompt, "options": options, "format": fmt},
                          sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def generate_json(self, prompt: str, schema: Optional[Dict[str, Any]] = None, seed: Optional[int] = 0,
                      num_predict: int = 256, system: Optional[str] = None, use_cache: bool = True) -> LLMResult:
        fmt: Any = schema if schema is not None else "json"      # a JSON schema or plain JSON mode
        opts = self.options(seed, num_predict)
        key = self.cache_key(prompt if system is None else f"{system}\n\n{prompt}", opts, fmt)
        path = self.cache_dir / f"{key}.json"
        if use_cache and path.exists():
            try:
                text = json.loads(path.read_text(encoding="utf-8"))["response"]
                self.hits += 1
                return LLMResult(text, extract_json(text), True, key)
            except (OSError, ValueError, KeyError):
                pass                                            # a damaged cache file is ignored
        body: Dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": False,
                                "format": fmt, "options": opts}
        if system is not None:
            body["system"] = system
        reply = self._post(self.url, body, self.timeout)
        self.calls += 1
        if not isinstance(reply, dict) or not isinstance(reply.get("response"), str):
            raise OllamaError(f"unexpected reply: {str(reply)[:200]}")
        text = reply["response"]
        if use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"model": self.model, "options": opts, "response": text},
                                      ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        return LLMResult(text, extract_json(text), False, key)
