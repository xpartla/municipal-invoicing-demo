import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs } from './pages/login';
import { CUSTOMERS, PROVIDER } from './seed';

// Prehľad klientov and Platforma (P2-M7-T04, plan §10.8, §10.9) pass axe in both themes and do
// not scroll sideways; staff and admins land on them (decision 67). Nothing is changed.

test('staff land on Prehľad klientov, which passes axe', async ({ page, checkA11y }) => {
  await loginAs(page, 'staff');
  await expect(page.getByRole('heading', { level: 1, name: 'Prehľad klientov' })).toBeVisible();
  const table = page.getByRole('region', { name: 'Klienti' });
  await expect(table.getByRole('link', { name: CUSTOMERS.boldog })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'light' });
});

test('admins land on Platforma and choose a provider in Prehľad klientov', async ({
  page,
  checkA11y,
}) => {
  await loginAs(page, 'admin');
  await expect(page.getByRole('heading', { level: 1, name: 'Platforma' })).toBeVisible();
  const counts = page.getByRole('list', { name: 'Počty' });
  await expect(counts.getByRole('link', { name: /Servisné účty/ })).toBeVisible();
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'light' });

  await page.goto('/provider');
  await expect(page.getByRole('heading', { level: 1, name: 'Prehľad klientov' })).toBeVisible();
  await page.getByRole('combobox', { name: 'Servisný účet' }).click();
  await page.getByRole('option', { name: PROVIDER }).click();
  await expect(
    page.getByRole('region', { name: 'Klienti' }).getByRole('link', { name: CUSTOMERS.second }),
  ).toBeVisible();
  await page.waitForLoadState('networkidle');
  await checkA11y();
});
