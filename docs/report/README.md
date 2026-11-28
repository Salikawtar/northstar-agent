# Report pages: one page each

**Main idea:** the report is 7 pages plus an appendix (`docs/report_plan.md`). This folder holds the one-page versions of pages 2 to 7, each condensed from the repository files, so every number has a source and a test.

| Page | File | Condensed from | Owner |
|---|---|---|---|
| 1 | `../decision_memo.md` | the pages below | Abhi |
| 2 | `page2_data.md` | `../data_quality.md`, `../generation_record.md`, `../data_dictionary.md` | Weidi |
| 3 | `page3_design_agents.md` | `../architecture.md`, `../edge_cases.md`, `../prompt_log.md` | Kawtar |
| 4 | `page4_finetune.md` | `../../src/northstar/finetune/study/README.md`, `../../src/northstar/finetune/MODEL_CARD.md`, `../evaluation_results.md` (section 3), `../economics.md` (section 5) | Neeraj |
| 5 | `page5_evaluation.md` | `../evaluation_results.md`, `../evaluation_rubric.md` | Libo |
| 6 | `page6_security.md` | `../operating_policy.md`, `../guardrails.md` | Jessica |
| 7 | `page7_economics.md` | `../economics.md` (sections 1 to 7) | Abhi |

**The numbers are checked.** `tests/test_report_pages.py` checks the numbers on every page against the data and the result files.

**One page each.** The same test fails if a page grows past the number of words that fit on one page at 11 pt with normal margins, tables and figure included. To add a sentence, cut one.

**Figures.**
- Page 3: `figures/architecture.png`, exported from `figures/architecture.mmd` (the diagram of `docs/architecture.md`, drawn left to right) with `mmdc -i figures/architecture.mmd -o figures/architecture.png -s 3 -b white`.
- Page 4: `src/northstar/finetune/study/results/page4_figure.png`, drawn by `python run_all.py finetune` (`src/northstar/finetune/study/report_figure.py`). The first version's figure (`src/northstar/finetune/results/page4_figure.png`) is kept with its model card.
- Page 7: `src/northstar/economics/results/cost_per_chat_vs_volume_page7.png`, drawn by `python run_all.py economics`.
