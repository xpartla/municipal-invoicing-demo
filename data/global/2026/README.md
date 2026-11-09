# Global code lists, budget year 2026

The four lists every municipality's lists are checked against (plan §6.1, §6.3). Public legal
data, read on 2026-11-08 from the official publications below. `riso seed` loads them as
version 1 of each global list for 2026; P2-M3 replaces the loader with import templates.

Each file is UTF-8 CSV with the header `code,name`, in the order of its source.

| File | Rows | List | Source |
|---|---|---|---|
| `ek.csv` | 691 | Economic classification (ekonomická klasifikácia): main categories, categories, položky (three digits) and podpoložky (six) | Opatrenie MF SR z 8. 12. 2004 č. MF/010175/2004-42, consolidated text effective from 1. 1. 2026 (as amended by MF/013361/2025-414, 20/2025 R. o.), annex part three, A. Príjmy to D. Prevody |
| `cofog.csv` | 216 | Functional classification (SK COFOG): oddiel, skupina, trieda, podtrieda | Vyhláška Štatistického úradu SR č. 257/2014 Z. z., version effective from 1. 1. 2015 (the latest; no amendment since), annex |
| `funding_sources.csv` | 285 | Funding sources (zdroje) for the budgets of municipalities and higher territorial units | Príručka na zostavenie návrhu rozpočtu verejnej správy na roky 2026 až 2028 (MF/007079/2025-41), Excel annex `Prilohy.xlsx`, sheet "Príloha č. 1_B" |
| `framework_accounts.csv` | 316 | Framework chart of accounts (rámcová účtová osnova) for municipalities: classes, groups, synthetic accounts | Opatrenie MF SR z 12. 12. 2022 č. MF/014454/2022-36 (oznámenie 484/2022 Z. z.) as amended by MF/014915/2023-361 (oznámenie 502/2023 Z. z.), consolidated text effective from 1. 1. 2024, annex |

URLs:

- EK: <https://static.slov-lex.sk/static/SK/OP/2025/20/20260101.html>, consolidated PDF <https://static.slov-lex.sk/pdf/prilohy/SK/OP/2025/20/20260101_5792656-2.pdf>
- COFOG: <https://static.slov-lex.sk/static/SK/ZZ/2014/257/20150101.html>
- Funding sources: the handbook <https://www.mfsr.sk/files/archiv/86/Prirucka-na-zostavenie-navrhu-rozpoctu-verejnej-spravy-na-roky-2026-az-2028.pdf>, its annex <https://www.mfsr.sk/files/archiv/57/Prilohy.xlsx> (linked from <https://www.mfsr.sk/sk/financie/financny-spravodajca/2025/>), and Dodatok č. 1 (MF/016074/2025-41) <https://mfsr.sk/files/archiv/4/Dodatok-c.1-k-Prirucke-na-zostavenie-navrhu-rozpoctu-verejnej-spravy-na-roky-2026-az-2028.pdf>
- Framework chart: the amendment <https://static.slov-lex.sk/static/SK/OP/2023/37/20240101.html>, consolidated PDF <https://static.slov-lex.sk/pdf/prilohy/SK/OP/2023/37/20240101_5592496-2.pdf>

## How the files were made

No source is published as a machine-readable list except the funding sources. The lists were
extracted by script from the official documents, not typed by hand:

- **EK and the framework chart**: the consolidated PDFs, converted with `pdftotext -layout`.
  An item is a line starting with its code; a wrapped name is joined back. Two PDF spacing
  artefacts were repaired ("Daňové príjm y" → "príjmy", a space before a comma).
- **COFOG**: the decree's HTML annex, which lists each code with its name.
- **Funding sources**: the code from the hierarchy columns B to F and the name from column G
  of sheet "Príloha č. 1_B". Annex 1/B is the list for municipal budgets; annex 1/A is the
  state budget's, where some codes mean something else (45 is "Vlastné zdroje štátneho fondu"
  in 1/A, "Dotácie poskytnuté zo štátneho fondu" in 1/B) and 41 and 72f do not exist.
  Dodatok č. 1 changes only annex 1/A (code 72k), so this file is unaffected.
- **Framework chart**: the annex names two ranges of groups without listing accounts,
  "75 až 79 - Podsúvahové účty" and "90 až 98 – Vnútroorganizačné účtovníctvo". They are
  written out as the groups 75 to 79 and 90 to 98 with those names. Classes 8 and 9, the
  groups 75 to 79 and 90 to 99 have no synthetic accounts in the chart: the entity defines
  them, so validation accepts any account in them.

Spot checks against the PDFs: the 2026 additions (632006 Elektrina, 632007 Plyn, 632008 Teplo,
112004 Dorovnávacia daň, 641021 to 641025, 721016 to 721020) are present; every code is unique
in its file.

## What Boldog's 2026 lists show against them

See `docs/phase2-log.md`, P2-M2-T03: Boldog's budget uses three EKs and four zdroje that the
2026 lists no longer have, five položky without their podpoložka, and 34 synthetic accounts
from the chart that preceded the 2022 measure.
