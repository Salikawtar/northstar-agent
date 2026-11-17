# Data quality: diversity in numbers and a protected test set

**For report page 2 (Weidi).** Two checks the brief's "Great" bucket asks for, both reproducible with no key and no cost. Dataset v1114, 200 conversations, 2026-11-17.

```bash
python -m northstar.datagen.diversity          # diversity numbers
python -m northstar.datagen.split --rebuild    # rebuild the 130 / 30 / 40 split and check it
```

## 1. Diversity (realism and diversity)

Faker values (names, plates, VINs, phones, emails, repair orders) are masked first, so the numbers measure the writing, not the random fill.

| Measure | Customer messages | Agent replies | What it means |
|---|---|---|---|
| distinct-2 (unique word pairs / all word pairs) | 0.644 | 0.667 | About two in three word pairs appear only once across the whole set |
| Mean similarity between two conversations (TF-IDF cosine, 0 to 1) | 0.094 | 0.070 | A typical pair of chats shares very little wording |
| Pairs above 0.5 similarity | 1 of 19,900 | 10 of 19,900 | Near-identical chats are almost absent |
| Most similar pair | 0.557 (v3_0125, v3_0213) | 0.695 | See the honest note below |
| Words per conversation (customer turns) | 81 | 38 | |

**By group (customer messages)**

| Group | Chats | distinct-2 | Mean similarity |
|---|---|---|---|
| English | 130 | 0.632 | 0.132 |
| French | 70 | 0.673 | 0.128 |
| Terse mobile typist | 23 | 0.902 | 0.069 |
| Angry owner, CAPS | 26 | 0.819 | 0.121 |
| Elderly, over-explains | 23 | 0.795 | 0.168 |
| Non-native English speaker | 25 | 0.779 | 0.171 |

- distinct-2 falls as a group gets bigger, so compare groups of similar size only (the 8 personas, 23 to 27 chats each, range 0.78 to 0.90).
- French is as varied as English, although one model wrote both.
- **Names:** 99 customers, 99 unique full names, 88 unique first names.
- **Realism controls applied:** mid-conversation corrections in 118 chats, fragments 75, French 70 (20 of them code-switched), CAPS 26, typos 23, non-native slips 25, over-explaining 23, writing for someone else 25.

**Honest note.** The most similar pair shows the one-voice risk of a single generator: two towing chats (v3_0125, v3_0213) reuse the same phrase ("towed by the city from in front of my place... a sign I've never seen before") with a different car, city and tone. It is the only pair above 0.5, but it is the kind of echo that several generator models would reduce (the course guide suggests two or three).

## 2. Train, validation and test kept apart

| Check | Result |
|---|---|
| Split | 130 train / 30 validation / 40 test |
| Rebuilt from the record | Exact: the generation run's 160 / 40 split replayed, plus the 32 moves logged in the QC_log sheet (30 to validation, 2 swapped), gives the dataset's split with 0 differences |
| Customers in two splits | 0 |
| Near-copies across splits (opening message, Faker masked, similarity >= 0.8) | 0. Closest pairs: train vs test 0.454, train vs validation 0.517, validation vs test 0.385 |
| Test chats reviewed by hand | 40 of 40 |
| Attack types in the test set | all 5 |

- The 30 validation rows were drawn on 2026-11-10 (grouped by customer, seed 894) in a notebook that was not kept as code, so the rebuild applies the logged moves rather than drawing them again. The checks above prove the protection on the data as it is.
- The test set is used once, at the end. Prompts are tuned on validation only.

## What page 2 should say

- Lead the quality-control story with the real fixes (28 agent replies that promised coverage, 14 incoherent chats, 22 fixes from the hand review), with 2 or 3 before and after examples from the QC_log.
- Say plainly that one generator (Claude) wrote the chats, and that the 15 rejected rows were written on purpose to test the filter rules (`docs/generation_record.md`, section 2).
- Use the diversity and split tables above as evidence, with the towing pair as the honest limit.
