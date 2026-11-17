"""Synthetic data generation (criterion 1). Owner: Weidi.

- pipeline.py       coverage matrix -> jobs -> prompt -> generator -> Faker fill -> QC filter -> rejection log -> grouped split
- export.py         turn a pipeline run into the conversations.csv column layout, and diff it against the dataset in data/
- build_redteam.py  the 75-attack red-team matrix (scaffold), and the checks on a filled red-team CSV

The recorded generation run that data/conversations/conversations.csv was built from is in data/source/generation/
(jobs matrix, generator output, rejected rows with reasons, prompt text and hash, run manifest). Replaying it needs no
key and no network. The team's later edits to the text and labels are logged in the QC_log sheet of the review workbook.
See docs/generation_record.md.
"""
