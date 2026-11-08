# Knowledge base, budget year 2026

Authored in M1 (plan section 6) and versioned by budget year, because the economic
classification changes each January. Since P2-M2 these files hold only what is true for every
municipality:

- `ek_su_bridge.yaml`: economic classification code to synthetic account, around forty rows.
- `cofog_map.yaml`: activity words and abbreviations to function codes, around thirty.
- `transfer_rules.yaml`: which zdroj codes expect a transfer.
- `lexicon.yaml`: around one hundred Slovak terms, abbreviations and spelling variants,
  matched without diacritics, including the credit-note markers.
- `style.yaml`: how the accountant writes the `text` of posting and budget lines.

A customer's own rules are its conventions (phase 2 plan §6.4): the analytic-account rules,
the canteen rule, local concepts and transfer overrides. Boldog's moved in P2-M2-T04 to
`data/conventions/00305863/2026.yaml` (they were `au_rules.yaml`, `canteen.yaml` and the
lexicon's `municipal_company`); the app keeps them per customer and year in the database.
`riso.knowledge.knowledge_for` merges the two for the file-based tools (`riso code`,
`riso eval`, `riso check`).
