import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, openNav } from './pages/login';

// Importy a exporty and the import wizard (P2-M3-T08) pass axe in both themes, at each step
// and with the transforms dialog, and fit the screen. The run ends cancelled, so no list
// changes for the other specs.

const CHART = [
  'Syntetický účet;Analytický účet;Druh účtu;Názov',
  '518;1;Nákladový;Telefóny',
  '321;0;Pasívny;Dodávatelia',
].join('\r\n');

test('Importy a exporty and each step of the import wizard pass axe', async ({
  page,
  checkA11y,
}) => {
  await loginAs(page, 'user');
  await openNav(page);
  await page.getByRole('link', { name: 'Importy a exporty' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Importy a exporty' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Šablóny mapovania' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'light' });

  await page.getByRole('link', { name: 'Nový import' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Nový import' })).toBeVisible();
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.locator('input[type="file"]').setInputFiles({
    name: 'rozvrh-axe.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(CHART, 'utf-8'),
  });
  await page.getByRole('button', { name: 'Nahrať a pokračovať' }).click();

  await expect(page.getByRole('region', { name: 'Ukážka súboru' })).toBeVisible();
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.getByRole('button', { name: 'Pokračovať na mapovanie' }).click();

  await expect(page.getByRole('region', { name: 'Mapovanie polí' })).toBeVisible();
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page
    .getByRole('button', { name: 'Upraviť – úpravy hodnoty poľa SU (syntetický účet)' })
    .click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await checkA11y();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();

  await page.getByRole('button', { name: 'Spustiť skúšobný import' }).click();
  await expect(page.getByText('Bez chýb.')).toBeVisible({ timeout: 15_000 });
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'light' });

  await page.getByRole('button', { name: 'Zrušiť import' }).click();
  await expect(page.getByText('Import je zrušený.')).toBeVisible();
});

test('the global lists’ import passes axe', async ({ page, checkA11y }) => {
  await loginAs(page, 'admin');
  await page.goto('/admin/codelists');
  await page.getByRole('link', { name: 'Importovať' }).click();
  await expect(
    page.getByRole('heading', { level: 1, name: 'Import globálneho číselníka' }),
  ).toBeVisible();
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
});
