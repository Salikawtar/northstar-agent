# Generation record: Northstar Motors synthetic conversations (generation run v3-conv / v1108, the base of v1114)

**What this is.** The record the course guide asks for with the synthetic data: how the 200 conversations were generated
(pipeline, prompt version, generator, planned models and temperatures, seed), what the filter rejected and why, how the rejects
were replaced, and how the first split was made. It covers the *generation* stage (run of 2026-11-07, exported as v1108 on
2026-11-08). Everything that happened after it (QC fixes, hand review, relabelling, the validation split) is logged change by
change in the QC_log sheet of `data/source/northstar_synthetic_dataset_v1114.xlsx` and summarised in section 7 below. Files
referenced here are in `data/source/generation/`.

## 1. Pipeline

`src/northstar/datagen/pipeline.py` (the file was `synth_data_pipeline.py` during the build): coverage matrix -> jobs ->
prompt per job -> generator -> JSON parse -> Faker fill -> QC filter -> rejection log -> regeneration of rejected jobs ->
grouped split -> export. One command reproduces v1108 from the recorded generator output:

```
python -m northstar.datagen.pipeline --jobs data/source/generation/jobs_designed.jsonl \
       --generations data/source/generation/generations_v3_conv.jsonl --seed 42 --out outputs/datagen
```

| Item | Value |
|---|---|
| Dataset version / prompt version | v1108 / v2 (prompt text in `prompt_v2.md`, sha256 `24cf172a5ac48935...`) |
| Seed | 42 (global); one Faker seed per customer, so a repeat customer keeps the same name, car, plate and RO |
| Jobs | 215 = 200 designed by the coverage matrix + 15 replacements for rejected jobs (`jobs_designed.jsonl`, column `designed`) |
| Generated / kept / rejected | 215 / 200 / 15 (validity 93%) |
| Coverage targets | 200 rows: 20 per intent; easy / hard / adversarial = 10 / 6 / 4 per intent; EN / FR = 13 / 7 per intent (130 / 70); 8 per attack type; 20 per hard mode; 25 per persona (`coverage_targets` in `run_manifest.json`) |
| First split | 160 train / 40 test, grouped by customer (`split_check` in `run_manifest.json`: 0 customers in both, max cross-split similarity 0.49); re-split by the team on 2026-11-10 to 130 / 30 / 40 (v1112) |

## 2. Generator, models and temperatures (read this before quoting the data section)

The pipeline is built for an 8-model OpenRouter rotation at 4 temperatures, assigned per job in `jobs_designed.jsonl`
(columns `model`, `temperature`; `top_p` 0.95):

- models: openai/gpt-4o-mini, openai/gpt-4.1-nano, google/gemini-2.5-flash-lite, meta-llama/llama-3.3-70b-instruct, mistralai/mistral-nemo, deepseek/deepseek-chat, qwen/qwen-2.5-7b-instruct, amazon/nova-lite-v1
- temperatures: 0.2, 0.7, 1.0, 1.3

**No OpenRouter key was available in the build session, so the rotation was not run.** The 215 conversations were written by
Claude (the chat assistant used to build the pipeline, `claude-fable-5-1`) acting as the generator through the pipeline's
generations-file mode: each job's prompt v2 was answered once, the answer was stored in `generations_v3_conv.jsonl` keyed by
job id, and the pipeline then parsed, filled, filtered and split that file exactly as it would live output. The `generator`
column of every record therefore reads `file` and `model` reads `claude-fable-5-1 (in-session stand-in)`; temperature was not
controlled and is recorded as null; the *planned* model and temperature of each job are kept in `planned_model` /
`planned_temperature`. Running the rotation now (`--live`, about $0.05 for 215 jobs) would produce a different dataset, which
would invalidate the hand review, the QC log and the recorded model runs built on v1114, so the team kept v1114 and records
the limitation here instead.

**The 15 rejected generations were written on purpose with the failure modes LLM generators produce** (a literal e-mail
address, "I hope this message finds you well", English where French was asked, a placeholder outside the vocabulary, a
near-copy of another job, a truncated JSON, an agent-first dialogue), so that every filter rule is exercised and logged on
this run. They are real rejections (the filter caught them, logged them, and the jobs were regenerated), but they are not a
measurement of a model's failure rate; a live run gives that number.

## 3. Filter: ten QC rules plus a near-duplicate pass

parse error, turn structure (customer first, roles alternate), label in the 10 intents, Faker field formats (regexes in
`run_manifest.json` > `qc.faker_formats`), length 15-2200 characters, unfilled placeholder, raw personal data in the
template, boilerplate phrases (word-boundary match), language mismatch (langdetect, else a script/stop-word fallback), and
near-duplicates: character 3-5-gram TF-IDF cosine on the opening customer turn in placeholder form, threshold 0.8
(true duplicates scored >= 0.95, the closest different pair 0.60). Two bugs in the course kit were found and fixed on the way:
its boilerplate check matched "here is a" inside "there is a scuff", and its duplicate check ran on filled text, where names
masked identical templates.

Rejections by reason: bad_turn_structure 1, raw_pii_in_template 3, unfilled_placeholder 3, boilerplate 2, near_duplicate_of 3, lang_mismatch 2, parse_error 1.

## 4. The 15 rejected rows (full text in `rejected.jsonl`, readable table in `rejected_15.csv`)

| id | intent | lang | reason | replaced by |
|---|---|---|---|---|
| v3_0012 | parts_order | en | bad_turn_structure:first turn is not the customer | v3_0201 |
| v3_0046 | parts_order | en | raw_pii_in_template | v3_0202 |
| v3_0067 | lease_end_return | en | unfilled_placeholder:contract_number | v3_0203 |
| v3_0081 | out_of_scope | en | raw_pii_in_template | v3_0204 |
| v3_0083 | lease_end_return | fr | boilerplate | v3_0205 |
| v3_0089 | recall_inquiry | en | near_duplicate_of:v3_0068 | v3_0206 |
| v3_0107 | warranty_claim | en | raw_pii_in_template | v3_0207 |
| v3_0121 | billing_dispute | en | boilerplate | v3_0208 |
| v3_0139 | recall_inquiry | fr | lang_mismatch:en!=fr | v3_0209 |
| v3_0144 | repair_status | fr | lang_mismatch:en!=fr | v3_0210 |
| v3_0160 | roadside_assistance | en | near_duplicate_of:v3_0008 | v3_0211 |
| v3_0164 | needs_human | en | near_duplicate_of:v3_0047 | v3_0212 |
| v3_0180 | out_of_scope | en | parse_error:json parse failed: Unterminated string starting at: line 1 column 41 (char 40) | v3_0213 |
| v3_0181 | lease_end_return | en | unfilled_placeholder:lease_number | v3_0214 |
| v3_0189 | parts_order | en | unfilled_placeholder:part_number | v3_0215 |

Each rejected job was re-issued with identical attributes (intent, difficulty, persona, language, customer) under a new id
(v3_0201 to v3_0215, `designed = 0`, `replaces = <old id>`), generated and filtered again, so the kept set matches the matrix in
every cell. The 15 originals stay in the log; nothing was edited to pass.

## 5. Red-team set

The 75 attacks (`data/redteam/redteam_75.csv`) were designed by the same pipeline (`build_redteam.py --scaffold`: 15 per
attack type, own customers in seed pools that never overlap the conversations, matrix in `redteam_jobs_designed.jsonl`).
The attack text was not generated by the pipeline: the scaffold left `attack_message` empty, a first draft was written from each
row's writing hint, and the team then rewrote all 75 by hand (workbook README, Human_checklist item 1).

## 6. Limits

Single generator and no temperature variation (section 2); the rejected rows are planted failure cases, not a measured model
failure rate; the duplicate check is lexical (paraphrases in other words pass); `langdetect` was not installable in the build
environment, so the language check used the fallback (it is now the default, so a replay gives the same result on every computer; `--lang-check langdetect` is optional); chat only, three turns, single-message attacks.

## 7. From the generation run to v1114 (what the team changed, from the QC_log sheet: 364 cell changes on the conversations)

The 200 ids and the 99 customers are unchanged, so every row in v1114 traces back to a job in `jobs_designed.jsonl`. What changed:

| Change | Size | Where logged |
|---|---|---|
| Em dashes replaced (a tell of AI-written text) | 197 removed in all: 183 by the punctuation rule, 14 inside rewritten text; 65 conversations changed only in punctuation | QC_log, rule "AI-style punctuation" (183); the rewrite rules for the other 14 |
| Text rewritten | 90 conversations: 28 agent replies that promised coverage, a refund or a waiver without checking (9 of them contradicting warranty_terms.json), 14 coherence fixes (model year after purchase date, "my father, Mélanie", corrections that repeated the same value), 22 team-review fixes, 21 booking dates moved after the mock "today" | QC_log, rules by name; reviewer notes in Conversations_200 |
| `needs_escalation` relabelled | 43 rows: all 28 adversarial chats (decision D-05), 13 contested billing charges (D-13), v3_0106 brake safety case (D-16), v3_0117 asks for a manager; 87 of 200 are now True | QC_log; Decisions sheet |
| `adversarial_type` retyped to warranty_fraud | 3 rows (v3_0007, v3_0119, v3_0177), so every attack type has 8. The workbook was built from the v3-conv export, before the v1108 bundle's own top-up of v3_0073 and v3_0129; the team's choice is the one in the data, and the v1108 versions of those two rows are not used | QC_log, rule "Rebalance warranty_fraud" |
| Split re-cut | 160 / 40 -> 130 / 30 / 40: 30 train rows moved to a validation split grouped by customer (seed 894); two single-customer rows swapped so the test set holds a PII-extraction case (v3_0078 to test, v3_0215 to train) | QC_log, rules "Validation split added", "Test set had no pii_extraction case" |
| Hand review | 74 rows read by the team (the 40 test rows + 34 rewritten rows): 52 keep, 22 fix, 0 reject | Conversations_200 review columns |

Net effect on the text: 155 of the 200 conversations differ from the generation output in at least one turn (65 only by punctuation, 90 by a logged rewrite); 45 are byte-for-byte the generator's output after Faker filling.
