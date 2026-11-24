# Data generation (`northstar.datagen`)

Owner: Weidi. The pipeline that produced the 200 conversations, the record of that run, and the checks that tie the
run to the dataset in `data/conversations/`.

## What is where

| Path | What it is |
|---|---|
| `src/northstar/datagen/pipeline.py` | The generator: coverage matrix -> jobs -> prompt v2 -> generator -> Faker fill -> 10 QC rules + near-duplicate check -> rejection log -> regeneration of rejected jobs -> grouped split -> export |
| `src/northstar/datagen/export.py` | Turns a run into the `conversations.csv` column layout and diffs it against the dataset |
| `src/northstar/datagen/build_redteam.py` | The 75-attack red-team matrix (scaffold) and the checks on the filled set |
| `data/source/generation/` | The recorded run: `jobs_designed.jsonl` (215 jobs with planned model and temperature), `generations_v3_conv.jsonl` (generator output per job), `rejected.jsonl` + `rejected_15.csv` (what was thrown out and why), `prompt_v2.md` (prompt text and SHA-256), `run_manifest.json`, `changelog.md`, `redteam_jobs_designed.jsonl` |
| `docs/generation_record.md` | The written record: prompt version, generator, models and temperatures, seed, rejected rows, replacement, first split, and what the team changed afterwards (section 7) |
| `tests/test_datagen.py` | Replays the run and checks it against the dataset (below) |

Everything the pipeline writes goes to `outputs/` (git-ignored). Nothing here overwrites `data/`.

## Replay the recorded run (no key, no network, about 6 seconds)

```bash
python -m northstar.datagen.pipeline --jobs data/source/generation/jobs_designed.jsonl \
    --generations data/source/generation/generations_v3_conv.jsonl --seed 42 --out outputs/datagen
python -m northstar.datagen.export --diff      # outputs/datagen/conversations_generated.csv, compared with data/conversations/conversations.csv
```

Expected: 215 generated, 200 kept, 15 rejected (reasons listed), split 160 / 40 with no customer in both. The diff shows
0 differences on ids, customers, request types, difficulties, personas, languages and Faker identifiers, and the
differences the team's QC log accounts for: 155 conversations with edited text (65 punctuation only, 90 rewritten),
43 `needs_escalation` relabels, 3 `adversarial_type` retypes, and the 130 / 30 / 40 re-split.

## Live run (writes a new dataset; do not replace v1114 with it)

Needs `OPENROUTER_API_KEY` in `.env`. Runs the 8-model x 4-temperature rotation planned in the jobs file (about $0.05):

```bash
python -m northstar.datagen.pipeline --jobs data/source/generation/jobs_designed.jsonl --seed 42 --out outputs/datagen_live
```

Use it to measure a real generator's rejection rate, not to regenerate the project data: the hand review, the QC log
and the recorded model runs all depend on the v1114 text.

## Diversity and the split check

```bash
python -m northstar.datagen.diversity          # distinct-2, similarity between chats, names (Faker masked)
python -m northstar.datagen.split --rebuild    # recorded 160 / 40 cut checked against the run's rules + 32 logged moves = the 130 / 30 / 40 split; overlap checks
```

Results: `docs/data_quality.md`.

## Red team

```bash
python -m northstar.datagen.build_redteam --check          # data/redteam/redteam_75.csv: 15 per type, no shared customers, no near-duplicates, no em dashes
python -m northstar.datagen.build_redteam --scaffold       # the matrix with attack_message empty -> outputs/datagen_redteam/
python -m northstar.datagen.build_redteam --from-csv FILE  # validate a hand-filled scaffold with the same QC rules, export to outputs/
```

## What the tests check (`pytest tests/test_datagen.py`)

- the prompt in the code has the SHA-256 recorded in the manifest (an un-bumped prompt edit would fail here)
- the replay keeps 200 and rejects 15 with the recorded reasons, and every rejection carries a reason
- the replayed ids, customers, request types, difficulties, personas, languages and Faker identifiers equal the dataset's
- the kept rows meet the coverage matrix (20 per intent, 130 EN / 70 FR, 8 per attack type)
- the replayed split is grouped by customer with no near-copies across it (its exact fold depends on the scikit-learn version, D-29)
- every Faker field in the dataset still has a valid format
- the red-team matrix in the code is the one behind `data/redteam/redteam_75.csv` (ids, attack types, customers, languages)

## Honest notes

The recorded run was written by one generator (Claude, through the generations-file mode) because no OpenRouter key
existed when the data was built, so temperature was not controlled; the 15 rejected rows were planted failure cases that
exercise every filter rule. Both are stated in `docs/generation_record.md`, section 2.
