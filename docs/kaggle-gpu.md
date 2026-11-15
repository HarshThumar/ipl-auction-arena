# Running the LLM bidders on a free Kaggle GPU

**Why:** on the laptop (no graphics card) one bidder decision takes about 20-170 seconds, so one
simulated auction (~1,200 decisions) takes 7+ hours. A free Kaggle GPU should bring this to about 1-2
seconds per decision, so one auction takes well under an hour. We still use **Ollama**, as on the
laptop (rule #9: everything validated runs on Ollama). The notebook measures the real speed in step 9.

**What it is:** Kaggle gives every verified account about **30 GPU hours a week** for free, in
sessions of up to 12 hours. The notebook `notebooks/kaggle_gpu.ipynb` installs Ollama there, downloads
the model, clones our **public** GitHub repo and runs the auction.

## One-time setup (about 15 minutes)

1. **Push the latest commits first.** The notebook clones the code from GitHub, so it only sees what
   is pushed.
2. **Create a Kaggle account** at kaggle.com with your **personal** email (not a work account).
3. **Verify your phone number:** profile picture → *Settings* → *Phone verification*. Without it,
   Kaggle gives no GPU and no internet.
4. **Import the notebook:** *Create* → *New Notebook* → menu *File* → *Import Notebook* → upload
   `notebooks/kaggle_gpu.ipynb` from the repo folder (or paste its GitHub URL).
5. **Settings panel** (right side of the notebook, "Session options"):
   - *Accelerator*: **GPU T4 x2**
   - *Internet*: **On**
   - Keep the notebook **Private** (the default). Making it public is a public action: ask first (rule #5).
6. Press **Run All**. The first run takes about 10 minutes:
   - installing Ollama takes about 1 minute;
   - downloading the model (about 5 GB) takes 2-4 minutes;
   - the tests take about 30 seconds.

## What each step does

| Step | What happens | Look for |
|---|---|---|
| 1 | Shows the GPU | `Tesla T4` |
| 2 | Settings: repo, model (`qwen2.5:7b`) | change `MODEL` here if needed |
| 3-4 | Installs and starts Ollama, one request at a time (same order every run) | a version line like `{"version":"..."}` |
| 5 | Downloads the model | `qwen2.5:7b` in the list |
| 6 | Clones the repo, installs requirements | the latest commit message |
| 7 | Restores saved LLM answers (optional) | `cached answers: N` |
| 8 | Runs the engine tests | `... passed` |
| 9 | **Speed test** | `median X s per decision` and hours per auction. **Tell Claude this number.** |
| 10 | One auction with code bidders | `rule violations: 0` |
| 11 | Your bidder, several seeds | per-seed summary |
| 12 | Saves logs and the LLM cache to `arena_runs.zip` | the file size |

## Every later session

- Open the notebook → check the GPU and Internet are still on → **Run All**.
- **Long runs (many seeds):** use *Save Version* → *Save & Run All (Commit)*. It runs in the
  background for up to 12 hours with the browser closed. The results appear in the version's *Output*.
- **Keep the LLM cache between sessions** (re-running a seed then costs nothing and gives the same log):
  1. After a run, open the version's *Output* → *New Dataset* → name it `arena-llm-cache`.
  2. Next time, *Add Input* → *Your Datasets* → `arena-llm-cache`. Step 7 copies it in.
- **Bring results to the laptop:** download `arena_runs.zip` from *Output* and unzip it into the repo
  folder. The `runs/` folder is gitignored, so it never gets committed by accident.

## Same model on the laptop

So that what you build on the laptop behaves like the cloud runs:

```
ollama pull qwen2.5:7b
set OLLAMA_MODEL=qwen2.5:7b          (PowerShell: $env:OLLAMA_MODEL = "qwen2.5:7b")
python scripts/bench_llm.py --n 2
```

`src/llm/ollama_client.py` reads `OLLAMA_MODEL` and `OLLAMA_HOST`, so the same code runs in both
places. Use the laptop for building and small checks, and Kaggle for anything with many decisions.

## Rules that still apply up there

- **Only the public repo goes to Kaggle.** Never upload `private/`, the official PDFs, or anything
  from work.
- Model calls run with temperature 0, a fixed seed and one request at a time. Even so, Ollama does not
  promise identical answers, so the **cache plus the event log** is what makes a run exactly repeatable.
- **Gemini is not used here.** It is only a fallback for the live forecast, never for backtests.

## If something goes wrong

| Symptom | Fix |
|---|---|
| No GPU, or `nvidia-smi` not found | Settings → Accelerator → GPU T4 x2; phone must be verified |
| `curl` / `git clone` fails | Settings → Internet → On |
| Step 4 says "ollama did not start" | Run step 4 again; the log tail is printed |
| Step 9 is slow (> 5 s per decision) | Check step 1 shows a GPU; check `ollama ps` shows `100% GPU` |
| Session stopped after ~20 min idle | Use *Save & Run All (Commit)* for long runs |
| Weekly GPU hours used up | They reset weekly; develop on the laptop meanwhile |
