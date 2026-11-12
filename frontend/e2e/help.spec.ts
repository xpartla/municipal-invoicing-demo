import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, openNav } from './pages/login';

// Pomocník (P2-M8-T01, plan §10.10) and the click-through's "Ako to funguje" scenario that
// decision 62 moved here (decision 68): the article opens from Pomocník and from a screen's
// "?", passes axe in both themes and fits the width, here at each of the three.

test('Ako to funguje opens from Pomocník and fits the screen', async ({ page, checkA11y }) => {
  await loginAs(page, 'user');
  await openNav(page);
  await page
    .getByRole('navigation', { name: 'Hlavné menu' })
    .getByRole('link', { name: 'Pomocník' })
    .click();
  await expect(page.getByRole('heading', { level: 1, name: 'Pomocník' })).toBeVisible();
  const group = page.getByRole('region', { name: 'Spracovanie faktúr' });
  await expect(group.getByRole('link')).toHaveCount(12);
  await expect(page.getByRole('region', { name: 'Pre administrátorov' })).toHaveCount(0);
  await checkA11y();

  await group.getByRole('link', { name: 'Ako to funguje' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Ako to funguje' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '5. Čo program nerobí' })).toBeVisible();
  await expect(page.getByText('Vstup z OCR (JSON)')).toBeVisible();
  expect(await scrollsHorizontally(page)).toBe(false);
  await checkA11y();
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
});

test('a screen\'s "?" opens its article, and the articles it links to, in the side panel', async ({
  page,
  checkA11y,
}) => {
  await loginAs(page, 'user');
  await expect(page.getByRole('heading', { level: 1, name: 'Domov' })).toBeVisible();
  await page.getByRole('button', { name: 'Pomocník k tejto obrazovke' }).click();
  const panel = page.getByRole('dialog', { name: 'Pomocník' });
  await expect(panel.getByRole('heading', { level: 3, name: 'Začíname' })).toBeVisible();

  await panel.getByRole('link', { name: 'Ako to funguje' }).click();
  await expect(panel.getByRole('heading', { level: 3, name: 'Ako to funguje' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'Domov' })).toBeAttached();
  expect(await scrollsHorizontally(page)).toBe(false);
  await checkA11y();

  await panel.getByRole('link', { name: 'Otvoriť ako stránku' }).click();
  await expect(page).toHaveURL(/\/help\/ako-to-funguje$/);
  await expect(page.getByRole('heading', { level: 1, name: 'Ako to funguje' })).toBeVisible();
  await expect(panel).toBeHidden();
});
