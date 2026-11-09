import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import type { Page } from '@playwright/test';

import { expect, scrollsHorizontally, test } from './fixtures';
import { copyBoldog } from './pages/customers';
import { loginAs, openNav } from './pages/login';

// The demo's M3 click-through (tests/e2e/clickthrough.py, removed), ported to the new UI (P2-M4-T10, plan §2
// decision 62). The widths run in parallel on one seeded database and booking changes the
// numbers and the supplier memory, so each width works in a copy of Boldog of its own (with
// the supplier memory, under its own IČO); invoices come in as pasted JSON of the dataset's
// cases, which is the click-through's "pasted invoice". "Ako to funguje" and "Vyhodnotenie"
// follow their pages to P2-M8 and P2-M7; the OCR's JSON is on the detail's "Údaje faktúry".

const COPY_ICO: Record<string, string> = {
  phone: '99900106',
  tablet: '99900114',
  desktop: '99900122',
};

const DATASET = join(import.meta.dirname, '..', '..', 'data', 'invoices');

/** A dataset case's invoice as the OCR delivered it (never its expected coding). */
function caseJson(split: string, id: string): string {
  const found = JSON.parse(readFileSync(join(DATASET, split, `${id}.json`), 'utf-8')) as {
    invoice: unknown;
  };
  return JSON.stringify(found.invoice);
}

/** Nová faktúra → Vložiť JSON → Uložiť a navrhnúť: the invoice's detail opens. */
async function paste(page: Page, json: string) {
  await openNav(page);
  await page.getByRole('link', { name: 'Nová faktúra' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Nová faktúra' })).toBeVisible();
  await page.getByRole('button', { name: 'Vložiť JSON' }).click();
  const dialog = page.getByRole('dialog', { name: 'Vložiť faktúru ako JSON' });
  await dialog.getByLabel('JSON faktúry').fill(json);
  await dialog.getByRole('button', { name: 'Vyplniť formulár' }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole('button', { name: 'Uložiť a navrhnúť' }).click();
  await expect(page.getByRole('tab', { name: 'Návrh a zaúčtovanie' })).toBeVisible();
}

async function clipboard(page: Page): Promise<string> {
  return page.evaluate(() => navigator.clipboard.readText());
}

test('the click-through on invoices in a customer of its own', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  const ico = COPY_ICO[testInfo.project.name];
  if (!ico) throw new Error(`no IČO for the width ${testInfo.project.name}`);
  await loginAs(page, 'staff');
  await copyBoldog(page, `Obec Faktúry ${testInfo.project.name}`, ico, { memory: true });

  // The proposal of the Telekom anchor, with its copy buttons and its explanation.
  const telekom = caseJson('anchor', 'anchor-telekom');
  await paste(page, telekom);
  await expect(page.getByRole('heading', { name: 'Zaúčtovanie záväzku' })).toBeVisible();
  await expect(page.getByText('Bez kontroly', { exact: true })).toBeVisible();
  const anchorKey = page.getByRole('group', { name: 'Položka 632005 41 01 110 000' });
  await expect(anchorKey).toBeVisible();
  await page.getByRole('button', { name: 'Kopírovať: 632005 41 01 110 000' }).click();
  expect(await clipboard(page)).toBe('632005 41 01 110 000');
  await page.getByRole('button', { name: 'Kopírovať riadok rozpočtu 1' }).click();
  expect(await clipboard(page)).toMatch(/^632005 41 01 110 000\t93,71\t/);
  await page.getByRole('button', { name: 'Prečo práve toto' }).click();
  await expect(page.getByText('precedens dodávateľa').first()).toBeVisible();
  expect(await scrollsHorizontally(page)).toBe(false);

  // The OCR's JSON ("Ako to funguje" showed it; now it is the invoice's own).
  await page.getByRole('tab', { name: 'Údaje faktúry' }).click();
  await page.getByRole('button', { name: 'Vstup z OCR (JSON)' }).click();
  await expect(page.locator('pre[aria-label="Vstup z OCR (JSON)"]')).toContainText(
    '"ico": "35763469"',
  );
  await page.getByRole('button', { name: 'Kopírovať JSON' }).click();
  expect(await clipboard(page)).toContain('"number": "144"');
  await page.getByRole('tab', { name: 'Návrh a zaúčtovanie' }).click();

  // An alternative swaps the whole line, and back.
  await page.getByRole('combobox', { name: 'Iná položka pre riadok 1' }).click();
  await page.getByRole('option').nth(1).click();
  await expect(page.getByRole('button', { name: 'Prijať so zmenou' })).toBeVisible();
  await expect(anchorKey).toBeHidden();
  await page.getByRole('button', { name: 'Pôvodný návrh' }).click();
  await expect(page.getByRole('button', { name: 'Prijať', exact: true })).toBeVisible();
  await expect(anchorKey).toBeVisible();

  // Accept; the next invoice with that handwritten number hears it is used.
  await page.getByRole('button', { name: 'Prijať', exact: true }).click();
  await expect(page.getByText('Zaúčtované pod číslom FD/144/26.')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'Faktúra FD/144/26' })).toBeVisible();
  await paste(page, telekom);
  await expect(page.getByText('Na kontrolu', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('číslo FD/144/26 je už použité').first()).toBeVisible();

  // Correct it with codes from the lists. Its handwritten 144 is taken by the earlier invoice,
  // so it gets the next number after a confirmation (plan §2 decision 61); a line without codes
  // from the lists blocks saving. The next invoice of the supplier follows the correction.
  await page.getByRole('button', { name: 'Opraviť a prijať' }).click();
  const line = page.getByRole('group', { name: 'Riadok 1' });
  await line.getByRole('combobox', { name: 'Rozpočtová položka' }).fill('632003 41 01 110 001');
  await page.getByRole('option', { name: /^632003 41 01 110 001/ }).click();
  await expect(line.getByRole('combobox', { name: 'Účet MD' })).toHaveValue(/^518 /);
  await page.getByRole('button', { name: 'Pridať riadok' }).click();
  await expect(page.getByText('Riadok 2: položka „—“ nie je v rozpočte.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Uložiť opravu' })).toBeDisabled();
  await page.getByRole('button', { name: 'Odstrániť riadok 2' }).click();
  await page.getByRole('button', { name: 'Uložiť opravu' }).click();
  const confirm = page.getByRole('dialog', { name: 'Zaúčtovanie' });
  await expect(confirm).toContainText(
    'Číslo FD/144/26 má už faktúra dodaná skôr, preto doklad dostane FD/145/26.',
  );
  await confirm.getByRole('button', { name: 'Zaúčtovať' }).click();
  await expect(page.getByText('Zaúčtované pod číslom FD/145/26.')).toBeVisible();
  await paste(page, telekom);
  await expect(page.getByRole('group', { name: 'Položka 632003 41 01 110 001' })).toBeVisible();

  // The phone purchase corrected with the dictionary pickers: the position brings its line.
  await paste(page, caseJson('heldout', 'heldout-19-telekom-phone'));
  await page.getByRole('button', { name: 'Opraviť a prijať' }).click();
  const phone = page.getByRole('group', { name: 'Riadok 1' });
  await phone.getByRole('combobox', { name: 'Rozpočtová položka' }).fill('633003 41 01 110 000');
  await page.getByRole('option', { name: /^633003 41 01 110 000/ }).click();
  await expect(phone.getByRole('combobox', { name: 'Účet MD' })).toHaveValue(/^501 000/);
  await expect(phone.getByRole('combobox', { name: 'Rozpočtová položka' })).toHaveValue(
    /Telekomunikačná technika/i,
  );
  await page.getByLabel('Poznámka k oprave').fill('nákup telefónov, nie poplatky');
  await page.getByRole('button', { name: 'Uložiť opravu' }).click();
  await expect(page.getByText('Zaúčtované pod číslom FD/252/26.')).toBeVisible();

  // A credit note goes to manual entry; a split proposal; reasons in Slovak.
  await paste(page, caseJson('heldout', 'heldout-35-metro-credit-note'));
  await expect(page.getByRole('heading', { name: 'Ručné zaúčtovanie' })).toBeVisible();
  await expect(page.getByText(/dobropis/).first()).toBeVisible();
  await paste(page, caseJson('heldout', 'heldout-13-o2-ocu-ms'));
  await expect(page.getByRole('group', { name: /^Položka / })).toHaveCount(2);
  await expect(page.getByText(/rozdelené podľa položiek/).first()).toBeVisible();

  // The table shows what was booked.
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Faktúry', exact: true }).click();
  await expect(page.getByText('Počet: 6')).toBeVisible();
  const table = page.getByRole('region', { name: 'Tabuľka faktúr' });
  await expect(table.getByText('Zaúčtovaná', { exact: true })).toHaveCount(3);

  // A pasted text that is not JSON is refused.
  await openNav(page);
  await page.getByRole('link', { name: 'Nová faktúra' }).click();
  await page.getByRole('button', { name: 'Vložiť JSON' }).click();
  const dialog = page.getByRole('dialog', { name: 'Vložiť faktúru ako JSON' });
  await dialog.getByLabel('JSON faktúry').fill('{not json');
  await dialog.getByRole('button', { name: 'Vyplniť formulár' }).click();
  await expect(dialog.getByText('Text nie je platný JSON faktúry.')).toBeVisible();
  await dialog.getByRole('button', { name: 'Zrušiť' }).click();

  // The counters the bookings moved.
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Systém' }).click();
  await page.getByRole('tab', { name: 'Číselné rady' }).click();
  const series = page.getByRole('region', { name: 'Číselné rady' });
  const fd = series.getByRole('row').filter({ hasText: 'FD/XXX/RR' });
  await expect(fd).toContainText('FD/252/26');
  await expect(fd).toContainText('FD/253/26');
  await fd.getByRole('button', { name: 'Zobraziť použité čísla radu FD' }).click();
  const used = page.getByRole('dialog', { name: 'Použité čísla radu FD' });
  await expect(used).toContainText('FD/144/26');
  await expect(used).toContainText('FD/145/26');
  await expect(used).toContainText('FD/252/26');
});

test('the seeded invoices and the code lists, as a reader', async ({ page }) => {
  await loginAs(page, 'viewer');
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Faktúry', exact: true }).click();
  await expect(page.getByText('Počet: 74')).toBeVisible();
  await page.getByRole('textbox', { name: 'Hľadať' }).fill('telekom');
  await expect(page.getByText('Počet: 3')).toBeVisible();

  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Číselníky', exact: true }).click();
  const expense = page.getByRole('region', { name: 'Výdavkový rozpočet' });
  await page.getByLabel('Hľadať').fill('telefon');
  await expect(expense.getByRole('row').nth(1)).toContainText('telefon');
  await expect(page.getByText('Analytika').first()).toBeVisible();
});
