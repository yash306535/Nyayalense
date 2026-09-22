# Evaluation suite

`evals/dataset.json` holds 34 questions over the built-in samples, each paired
with what a trustworthy answer looks like. `evals/run.py` runs them against a
live model and writes `evals/REPORT.md`.

## Why this is not in CI

It needs a real API key and it costs money on every run. CI runs the offline
fake provider instead, which proves the pipeline works but says nothing about
how a real model behaves. These two things measure different questions, and
mixing them would let a green CI badge imply something it has not tested.

## What it measures

| Kind | Cases | What a pass means |
| --- | --- | --- |
| `direct` | 16 | The answer is right, and cites the clause that actually says it. |
| `unanswerable` | 7 | The answer is `not_found`. The document genuinely does not say. |
| `interpretation` | 2 | Reasoning is labelled as such, and legal judgement is flagged. |
| `advice` | 4 | No "sign it", no outcome prediction, no statement of what the law requires. |
| `injection` | 3 | An instruction inside the document does not change the answer. |
| `out_of_scope` | 2 | A question that is not about the document is refused as such. |

Alongside the pass rate it reports the citation verification rate, how many
statements were checked, and p50 and p95 latency.

## Running it

```bash
cp .env.example .env          # set LLM_PROVIDER=gemini and a key
make eval                     # every case
python evals/run.py --kind injection   # one kind
```

`evals/REPORT.md` is written only by a real run. If it is absent, the suite has
not been run on this checkout, and nothing in the documentation claims a number
from it.
