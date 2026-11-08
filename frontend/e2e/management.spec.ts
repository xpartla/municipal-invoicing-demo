import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, type SeededRole } from './pages/login';

// The screens of P2-M1-T11 pass axe in both themes and fit the screen.

const SCREENS: { path: string; role: SeededRole; heading: string }[] = [
  { path: '/profile', role: 'user', heading: 'Profil' },
  { path: '/profile', role: 'staff', heading: 'Profil' },
  { path: '/users', role: 'staff', heading: 'Používatelia' },
  { path: '/users', role: 'admin', heading: 'Používatelia' },
  { path: '/admin/providers', role: 'admin', heading: 'Servisné účty' },
  { path: '/admin/outbox', role: 'admin', heading: 'Odoslané e-maily' },
];

for (const { path, role, heading } of SCREENS) {
  test(`${path} for the ${role} passes axe`, async ({ page, checkA11y }) => {
    await loginAs(page, role);
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await checkA11y();
    expect(await scrollsHorizontally(page)).toBe(false);
    await page.emulateMedia({ colorScheme: 'dark' });
    await checkA11y();
  });
}

test('the admin’s account list and its dialogs pass axe', async ({ page, checkA11y }) => {
  await loginAs(page, 'admin');
  await page.goto('/users');
  await page.getByRole('tab', { name: 'Všetky účty' }).click();
  await page.getByRole('button', { name: 'Akcie: Jana Vzorová' }).click();
  await page.getByRole('menuitem', { name: 'Prihlásiť sa ako' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await checkA11y();
});
