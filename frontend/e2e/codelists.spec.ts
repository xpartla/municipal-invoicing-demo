import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, openNav } from './pages/login';

// Číselníky and Globálne číselníky (P2-M2-T08) pass axe in both themes, with their dialogs,
// and fit the screen.

test('Číselníky with the row dialog and the history pass axe', async ({ page, checkA11y }) => {
  await loginAs(page, 'user');
  await openNav(page);
  await page.getByRole('link', { name: 'Číselníky' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Číselníky' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Výdavkový rozpočet' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'light' });

  await page.getByRole('button', { name: 'Pridať riadok' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await checkA11y();
  await page.getByRole('button', { name: 'Zrušiť' }).click();

  await page.getByRole('button', { name: 'Verzie a zmeny' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Verzie' })).toBeVisible();
  await checkA11y();
});

test('Globálne číselníky pass axe', async ({ page, checkA11y }) => {
  await loginAs(page, 'admin');
  await page.goto('/admin/codelists');
  await expect(page.getByRole('heading', { level: 1, name: 'Globálne číselníky' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Globálne číselníky podľa rokov' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Ekonomická klasifikácia' })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
});
