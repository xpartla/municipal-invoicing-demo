# Knowledge base, budget year 2026

Authored in M1 (plan section 6) and versioned by budget year, because the economic
classification changes each January. Planned files:

- `ek_su_bridge.yaml`: economic classification code to synthetic account, around forty rows.
- `au_rules.yaml`: how to pick the analytic account within 501, 502, 518, 321, 527 and 548.
- `cofog_map.yaml`: activity words and abbreviations to function codes, around thirty.
- `transfer_rules.yaml`: which zdroj codes expect a transfer.
- `canteen.yaml`: the canteen food rule: series FDŠJ, debit 501 080, credit 321 080, zdroj 72f,
  function 09 601.
- `lexicon.yaml`: around one hundred Slovak terms, abbreviations and spelling variants,
  matched without diacritics, including the credit-note markers.
- `style.yaml`: how the accountant writes the `text` of posting and budget lines.
