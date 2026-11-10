import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, openNav } from './pages/login';

// Faktúra (P2-M4-T08) passes axe in both themes: the proposal with its cards, the correction
// editor, "Prečo práve toto", the fields with the OCR's JSON, and the history. Nothing is
// booked, so the other specs see the seeded state.

test('the invoice detail passes axe in each of its parts', async ({ page, checkA11y }) => {
  await loginAs(page, 'user');
  await openNav(page);
  await page.getByRole('link', { name: 'Faktúry' }).click();
  await page.getByRole('textbox', { name: 'Hľadať' }).fill('8390051427');
  const table = page.getByRole('region', { name: 'Tabuľka faktúr' });
  await expect(table.getByRole('row')).toHaveCount(2);
  await table.getByRole('link', { name: 'FD/144/26' }).click();
  await expect(page.getByRole('heading', { name: 'Zaúčtovanie záväzku' })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Položka 632005 41 01 110 000' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'light' });

  await page.getByRole('button', { name: 'Prečo práve toto' }).click();
  await expect(page.getByText('precedens dodávateľa').first()).toBeVisible();
  await checkA11y();

  await page.getByRole('button', { name: 'Opraviť a prijať' }).click();
  await expect(page.getByRole('group', { name: 'Riadok 1' })).toBeVisible();
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.getByRole('button', { name: 'Zrušiť', exact: true }).click();

  await page.getByRole('tab', { name: 'Údaje faktúry' }).click();
  await page.getByRole('button', { name: 'Vstup z OCR (JSON)' }).click();
  await expect(page.getByText(/"handwritten"/)).toBeVisible();
  await checkA11y();

  await page.getByRole('tab', { name: 'História' }).click();
  await expect(page.getByRole('cell', { name: 'Vytvorená' })).toBeVisible();
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
});
