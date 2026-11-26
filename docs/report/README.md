# Report pages: one-page drafts

**Main idea:** the report is 7 pages plus an appendix (`docs/report_plan.md`). This folder holds one-page drafts of four of them, each condensed from the repository files, so every number has a source and a test.

| Page | File | Condensed from | Owner |
|---|---|---|---|
| 1 | `../decision_memo.md` | the pages below | Abhi |
| 2 | `page2_data.md` | `../data_quality.md`, `../generation_record.md`, `../data_dictionary.md` | Weidi |
| 3 | `page3_design_agents.md` | `../architecture.md`, `../edge_cases.md`, `../prompt_log.md` | Kawtar |
| 6 | `page6_security.md` | `../operating_policy.md`, `../guardrails.md` | Jessica |
| 7 | `page7_economics.md` | `../economics.md` (sections 1 to 7) | Abhi |

Pages 4 and 5 are drafted by Neeraj and Libo outside this folder.

**They are drafts.** Each owner edits their page. The numbers should stay as they are: `tests/test_report_pages.py` checks them against the data and the result files.

**One page each.** The same test fails if a page grows past the number of words that fit on one page at 11 pt with normal margins, tables and figure included. To add a sentence, cut one.

**Figures.**
- Page 3: `figures/architecture.png`, exported from `figures/architecture.mmd` (the diagram of `docs/architecture.md`, drawn left to right) with `mmdc -i figures/architecture.mmd -o figures/architecture.png -s 3 -b white`.
- Page 7: `src/northstar/economics/results/cost_per_chat_vs_volume_page7.png`, drawn by `python run_all.py economics`.
