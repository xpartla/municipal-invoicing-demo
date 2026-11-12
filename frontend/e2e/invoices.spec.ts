import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, openNav } from './pages/login';

// Faktúry (P2-M4-T07) passes axe in both themes: the table, the further filters, a
// selection with its bulk actions, the column chooser and the export dialog. A filter goes to
// the URL. Nothing is changed: the seeded invoices are not booked, so there is nothing to
// export, and the selection is cleared.

test('the invoice table, its filters, the bulk bar and the export dialog pass axe', async ({
  page,
  checkA11y,
}) => {
  // Six axe passes over a page of 50 rows take 20–28 s alone; more under a full parallel run.
  test.setTimeout(60_000);
  await loginAs(page, 'user');
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Faktúry' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Faktúry' })).toBeVisible();
  const table = page.getByRole('region', { name: 'Tabuľka faktúr' });
  await expect(table.getByRole('row')).toHaveCount(51); // the header and a page of 50
  await expect(page.getByText(/^Počet: \d+$/)).toBeVisible();
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'light' });

  await page.getByRole('textbox', { name: 'Hľadať' }).fill('telekom');
  await expect(page).toHaveURL(/q=telekom/);
  await expect(page.getByText('Aktívne filtre: 1')).toBeVisible();
  await expect(table.getByRole('row')).not.toHaveCount(51);

  await page.getByRole('button', { name: 'Ďalšie filtre' }).click();
  await expect(page.getByLabel('Suma od')).toBeVisible();
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);

  await table.getByRole('checkbox').nth(1).check();
  await expect(page.getByText('Vybrané: 1')).toBeVisible();
  await checkA11y();
  await page.getByRole('button', { name: 'Zrušiť výber' }).click();

  await page.getByRole('button', { name: 'Stĺpce' }).click();
  await expect(page.getByRole('checkbox', { name: 'MD / DAL' })).toBeVisible();
  await checkA11y();
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: 'Exportovať' }).click();
  const dialog = page.getByRole('dialog', { name: 'Export faktúr' });
  await expect(dialog.getByText(/Nie je čo exportovať/)).toBeVisible();
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'light' });
  await dialog.getByRole('button', { name: 'Zrušiť' }).click();
});
