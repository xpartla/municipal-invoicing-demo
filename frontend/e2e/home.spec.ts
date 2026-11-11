import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs } from './pages/login';

// Domov (P2-M7-T03, plan §10.2) passes axe in both themes, with its charts and with their
// table views, and does not scroll sideways. The seeded invoices came in on 1 January 2026,
// so that month has them; nothing is changed.

test('Domov with its tiles, charts and tables passes axe', async ({ page, checkA11y }) => {
  await loginAs(page, 'user');
  await expect(page.getByRole('heading', { level: 1, name: 'Domov' })).toBeVisible();
  const customerPath = new URL(page.url()).pathname;
  await page.goto(`${customerPath}?month=2026-01`);
  const tiles = page.getByRole('list', { name: 'Ukazovatele mesiaca' });
  await expect(tiles.getByRole('link', { name: /Nahrané\s*74/ })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Začíname', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Vyžaduje pozornosť', exact: true })).toContainText(
    'Čakajú najdlhšie (74)',
  );
  await expect(
    page.getByRole('region', { name: /^Číselné rady/ }).getByRole('row'),
  ).not.toHaveCount(0);
  await page.waitForLoadState('networkidle');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'light' });

  // Nothing is booked yet: the charts give their summary alone.
  await expect(
    page.getByRole('region', { name: 'Zaúčtované podľa dní', exact: true }),
  ).toContainText('V tomto mesiaci sa nič nezaúčtovalo.');
  await expect(
    page.getByRole('region', { name: 'Zaúčtované za 12 mesiacov', exact: true }),
  ).toContainText('február 2025 – január 2026: 0 faktúr za 0,00');

  // A tile opens the invoice table with its filter.
  await tiles.getByRole('link', { name: /Na kontrolu/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Faktúry' })).toBeVisible();
  await expect(page).toHaveURL(/uploaded_from=2026-01-01/);
  await expect(page).toHaveURL(/needs_review/);
});
