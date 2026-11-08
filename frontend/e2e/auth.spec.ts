import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, openNav, type SeededRole } from './pages/login';
import { USERS } from './seed';

// The pages of P2-M1-T10: the ones before a login, and the shell per role. Each passes axe,
// logs no errors and does not scroll sideways.

for (const path of ['/login', '/forgot-password', '/invitation#not-a-token']) {
  test(`${path} passes axe`, async ({ page, checkA11y }) => {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await checkA11y();
    expect(await scrollsHorizontally(page)).toBe(false);
  });
}

const LANDING: Record<SeededRole, RegExp> = {
  admin: /\/users$/,
  staff: /\/users$/,
  user: /\/c\/[0-9a-f-]+$/,
  viewer: /\/c\/[0-9a-f-]+$/,
};

for (const role of Object.keys(USERS) as SeededRole[]) {
  test(`the shell of the ${role} passes axe in both themes`, async ({ page, checkA11y }) => {
    await loginAs(page, role);
    await expect(page).toHaveURL(LANDING[role]);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await openNav(page);
    await checkA11y();
    expect(await scrollsHorizontally(page)).toBe(false);
    await page.emulateMedia({ colorScheme: 'dark' });
    await checkA11y();
  });
}

test('a wrong password says so', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('E-mail').fill(USERS.viewer.email);
  await page.getByLabel('Heslo', { exact: true }).fill('Zlé-heslo-celkom-iste');
  await page.getByRole('button', { name: 'Prihlásiť sa' }).click();
  await expect(page.getByRole('alert')).toHaveText('Nesprávny e-mail alebo heslo.');
});

test('logging out returns to the login', async ({ page }) => {
  await loginAs(page, 'user');
  await openNav(page);
  await page.getByRole('button', { name: 'Odhlásiť' }).click();
  await expect(page.getByText('Odhlásenie prebehlo.')).toBeVisible();
  await page.goto('/messages');
  await expect(page).toHaveURL(/\/login\?next=/);
});
