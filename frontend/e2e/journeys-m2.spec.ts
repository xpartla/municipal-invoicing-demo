import { expect, test } from './fixtures';
import { copyBoldog } from './pages/customers';
import { loginAs, openNav } from './pages/login';

// The journeys of P2-M2 (plan §13.2). The three widths run in parallel on one seeded
// database, so the journeys that write take a list and a parameter of their own per width.

const LIST_OF: Record<string, { tab: string; key: string; field: string }> = {
  phone: { tab: 'Číselné rady dokladov', key: 'FD', field: 'Popis' },
  tablet: { tab: 'Transfery', key: '312001 111 000', field: 'Názov' },
  desktop: { tab: 'Účtový rozvrh', key: '518 003', field: 'Popis' },
};

async function openCodelists(page: Parameters<typeof loginAs>[0]) {
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Číselníky' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Číselníky' })).toBeVisible();
}

test('1. searching the expense budget for "telefon" finds 632005', async ({ page }) => {
  await loginAs(page, 'viewer');
  await openCodelists(page);
  await page.getByLabel('Hľadať').fill('telefon');
  const table = page.getByRole('region', { name: 'Výdavkový rozpočet' });
  await expect(table.getByRole('cell', { name: '632005' }).first()).toBeVisible();
  await expect(table.getByRole('cell', { name: /^telefon/i }).first()).toBeVisible();
});

test('2. editing a row makes a new version and keeps the old one in the history', async ({
  page,
}, testInfo) => {
  const target = LIST_OF[testInfo.project.name] ?? LIST_OF.desktop;
  if (!target) throw new Error('no list for this width');
  const text = `Upravené v teste (${testInfo.project.name})`;
  await loginAs(page, 'user');
  await openCodelists(page);
  await page.getByRole('tab', { name: target.tab }).click();
  await page.getByLabel('Hľadať').fill(target.key);
  await page.getByRole('button', { name: `Akcie: ${target.key}`, exact: true }).click();
  await page.getByRole('menuitem', { name: 'Upraviť' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel(new RegExp(`^${target.field}`)).fill(text);
  await dialog.getByRole('button', { name: 'Uložiť' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('region', { name: target.tab }).getByText(text)).toBeVisible();

  await page.getByRole('button', { name: 'Verzie a zmeny' }).click();
  const history = page.getByRole('dialog');
  const versions = history.getByRole('region', { name: 'Verzie' });
  await expect(versions.getByRole('row')).toHaveCount(3); // header, version 2, version 1
  await history.getByRole('button', { name: 'Zmeny 1 → 2' }).click();
  await expect(history.getByRole('region', { name: 'Zmeny z verzie 1 na 2' })).toContainText(text);
});

// Journey 3 changes the parameters in a copy of Boldog: Boldog's own are read by the other
// specs (a series without a pattern stops its coding, P2-M4-T10).
// An IČO per attempt: a retry cannot copy under the IČO its first attempt took.
const PARAMETER_OF: Record<string, { field: string; value: string; icos: readonly string[] }> = {
  phone: { field: 'Predvolená rada', value: 'FX', icos: ['99900131', '99900190'] },
  tablet: { field: 'Rada školskej jedálne', value: 'FDŠX', icos: ['99900149', '99900203'] },
  desktop: { field: 'Predvolený zdroj', value: '43', icos: ['99900157', '99900211'] },
};

test('3. editing the parameters', async ({ page }, testInfo) => {
  const width = PARAMETER_OF[testInfo.project.name];
  if (!width) throw new Error(`no parameter for the width ${testInfo.project.name}`);
  const { field, value } = width;
  const ico = width.icos[testInfo.retry];
  if (!ico) throw new Error(`no IČO for attempt ${String(testInfo.retry + 1)}`);
  await loginAs(page, 'staff');
  const name = `Obec Parametre ${testInfo.project.name} ${String(testInfo.retry + 1)}`;
  await copyBoldog(page, name, ico);
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Systém' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Systém' })).toBeVisible();
  const input = page.getByLabel(new RegExp(`^${field}`));
  await input.fill(value);
  await page.getByRole('button', { name: 'Uložiť' }).click();
  await expect(page.getByText('Uložené.')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel(new RegExp(`^${field}`))).toHaveValue(value);
});

test('4. a viewer cannot edit', async ({ page }) => {
  await loginAs(page, 'viewer');
  await openCodelists(page);
  await expect(page.getByRole('region', { name: 'Výdavkový rozpočet' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pridať riadok' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /^Akcie:/ })).toHaveCount(0);
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Systém' }).click();
  await expect(page.getByLabel(/^Predvolená rada/)).toHaveAttribute('readonly', '');
  await expect(page.getByRole('button', { name: 'Uložiť' })).toHaveCount(0);
});
