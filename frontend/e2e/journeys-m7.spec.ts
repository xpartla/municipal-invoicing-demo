import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import type { Page } from '@playwright/test';

import { expect, scrollsHorizontally, test } from './fixtures';
import { copyBoldog } from './pages/customers';
import { loginAs, openNav } from './pages/login';
import { CUSTOMERS, USERS } from './seed';

// The M7 journeys (P2-M7-T07, plan §13.2): Domov after a booking shows the counts, a
// provider's overview of its customers, and the admin's audit search. The booking happens in a
// copy of Boldog of its own per width and attempt (placeholder IČOs that pass the check digit
// and are used nowhere else), so the widths running in parallel do not disturb each other.

const COPY_ICO: Record<string, readonly string[]> = {
  phone: ['99900602', '99900611'],
  tablet: ['99900629', '99900637'],
  desktop: ['99900645', '99900653'],
};

const DATASET = join(import.meta.dirname, '..', '..', 'data', 'invoices');

function caseJson(split: string, id: string): string {
  const found = JSON.parse(readFileSync(join(DATASET, split, `${id}.json`), 'utf-8')) as {
    invoice: unknown;
  };
  return JSON.stringify(found.invoice);
}

async function paste(page: Page, json: string) {
  await openNav(page);
  await page.getByRole('link', { name: 'Nová faktúra' }).click();
  await page.getByRole('tab', { name: 'Zadať ručne' }).click();
  await page.getByRole('button', { name: 'Vložiť JSON' }).click();
  const dialog = page.getByRole('dialog', { name: 'Vložiť faktúru ako JSON' });
  await dialog.getByLabel('JSON faktúry').fill(json);
  await dialog.getByRole('button', { name: 'Vyplniť formulár' }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole('button', { name: 'Uložiť a navrhnúť' }).click();
  await expect(page.getByRole('tab', { name: 'Návrh a zaúčtovanie' })).toBeVisible();
}

test('Domov after a booking shows the counts', async ({ page, checkA11y }, testInfo) => {
  test.setTimeout(120_000);
  const ico = COPY_ICO[testInfo.project.name]?.[testInfo.retry];
  if (!ico) throw new Error(`no IČO for the width ${testInfo.project.name}`);
  await loginAs(page, 'staff');
  const name = `Obec Domov ${testInfo.project.name} ${String(testInfo.retry + 1)}`;
  await copyBoldog(page, name, ico, { memory: true });

  // Nothing yet this month.
  const tiles = page.getByRole('list', { name: 'Ukazovatele mesiaca' });
  await expect(tiles.getByRole('link', { name: /Nahrané\s*0/ })).toBeVisible();
  await expect(tiles.getByRole('link', { name: /^Zaúčtované\s*0/ })).toBeVisible();

  // Two invoices entered; one booked.
  await paste(page, caseJson('anchor', 'anchor-telekom'));
  await page.getByRole('button', { name: 'Prijať', exact: true }).click();
  await expect(page.getByText('Zaúčtované pod číslom FD/144/26.')).toBeVisible();
  await paste(page, caseJson('anchor', 'anchor-dpo'));

  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Domov' }).click();
  await expect(tiles.getByRole('link', { name: /Nahrané\s*2/ })).toBeVisible();
  await expect(tiles.getByRole('link', { name: /^Zaúčtované\s*1/ })).toBeVisible();
  await expect(tiles.getByRole('link', { name: /Suma zaúčtovaných\s*93,71/ })).toBeVisible();
  const perDay = page.getByRole('region', { name: 'Zaúčtované podľa dní', exact: true });
  await expect(perDay).toContainText(/Spolu 1 faktúra; najviac 1 dňa/);
  await perDay.getByText('Tabuľka', { exact: true }).click();
  await expect(perDay.getByRole('table').getByRole('row')).toHaveCount(2);
  await expect(page.getByRole('region', { name: 'Podľa druhu', exact: true })).toContainText(
    '93,71',
  );
  await expect(
    page.getByRole('region', { name: 'Najčastejší dodávatelia', exact: true }),
  ).toContainText('Slovak Telekom');
  await expect(page.getByRole('region', { name: 'Začíname', exact: true })).toContainText(
    'Zaúčtujte prvú faktúru',
  );
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);

  // The booked tile opens the bookings of the month.
  await tiles.getByRole('link', { name: /^Zaúčtované\s*1/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Faktúry' })).toBeVisible();
  await expect(page).toHaveURL(/booked_from=/);
  await expect(page.getByText('Počet: 1')).toBeVisible();
});

test("a provider's overview of its customers", async ({ page, checkA11y }) => {
  await loginAs(page, 'staff');
  // Staff land on Prehľad klientov (plan §2 decision 67).
  await expect(page.getByRole('heading', { level: 1, name: 'Prehľad klientov' })).toBeVisible();
  const totals = page.getByRole('list', { name: 'Súčty za všetkých klientov' });
  await expect(totals).toBeVisible();
  const table = page.getByRole('region', { name: 'Klienti', exact: true });
  await expect(table.getByRole('link', { name: CUSTOMERS.boldog })).toBeVisible();
  await expect(table.getByRole('link', { name: CUSTOMERS.second })).toBeVisible();
  await expect(table.getByRole('link', { name: CUSTOMERS.unassigned })).toHaveCount(0);
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await table.getByRole('link', { name: CUSTOMERS.second }).click();
  await expect(page.getByText(`Prehľad klienta ${CUSTOMERS.second}`)).toBeVisible();
  // The customer has no lists for this year: Domov says so.
  await expect(page.getByRole('region', { name: 'Vyžaduje pozornosť', exact: true })).toContainText(
    'Chýba číselník',
  );
});

test("the admin's audit search", async ({ page, checkA11y }) => {
  await loginAs(page, 'admin');
  await expect(page.getByRole('heading', { level: 1, name: 'Platforma' })).toBeVisible();
  await page
    .getByRole('list', { name: 'Počty' })
    .getByRole('link', { name: /Prihlásenia/ })
    .click();
  await expect(page.getByRole('heading', { level: 1, name: 'Audit' })).toBeVisible();
  await page.getByRole('textbox', { name: 'Akcia' }).fill('auth.login');
  await page.getByRole('button', { name: 'Hľadať' }).click();
  await expect(page).toHaveURL(/action=auth\.login/);
  const table = page.getByRole('region', { name: 'Záznamy auditu', exact: true });
  await expect(table.getByRole('row').nth(1)).toContainText('auth.login');
  await expect(table).toContainText(USERS.admin.name);
  await page.getByRole('main').getByRole('combobox', { name: 'Klient' }).click();
  await page.getByRole('option', { name: CUSTOMERS.boldog }).click();
  await expect(page).toHaveURL(/customer=/);
  await page.getByRole('textbox', { name: 'Akcia' }).fill('');
  await page.getByRole('button', { name: 'Hľadať' }).click();
  await expect(table.getByRole('row').nth(1)).toContainText(CUSTOMERS.boldog);
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
});
