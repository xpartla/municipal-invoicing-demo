import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, openNav } from './pages/login';

// Nový klient (P2-M3-T09) passes axe at each step, in both themes, and fits the screen. It
// stops before creating, so the other specs see the seeded customers only.

test('each step of Nový klient passes axe', async ({ page, checkA11y }) => {
  await loginAs(page, 'staff');
  await openNav(page);
  await page.getByRole('link', { name: 'Používatelia' }).click();
  await page.getByRole('link', { name: 'Nový klient' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Nový klient' })).toBeVisible();
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);

  await page.getByRole('radio', { name: /Kópia jedného z vašich klientov/ }).check();
  await page.getByRole('combobox', { name: 'Kopírovať z klienta' }).click();
  await page.getByRole('option', { name: /Obec Boldog/ }).click();
  await checkA11y();
  await page.getByRole('button', { name: 'Ďalej' }).click();

  await expect(page.getByRole('textbox', { name: /^Názov/ })).toBeVisible();
  await page.getByRole('textbox', { name: /^Názov/ }).fill('Obec Axe');
  await page.getByRole('textbox', { name: /^IČO/ }).fill('99900050');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.getByRole('button', { name: 'Ďalej' }).click();

  await expect(page.getByRole('checkbox', { name: 'Pamäť dodávateľov' })).not.toBeChecked();
  await checkA11y();
  await page.getByRole('button', { name: 'Ďalej' }).click();

  await page.getByRole('checkbox', { name: 'Pozvať prvé prihlásenie' }).check();
  await expect(page.getByRole('textbox', { name: 'E-mail' })).toBeVisible();
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
});
