import { expect, scrollsHorizontally, test } from './fixtures';
import { CUSTOMERS, SEED_PASSWORD, USERS } from './seed';

// The shell loads, is accessible and fits the screen, at each project's width.

test('the shell loads without errors, passes axe and does not scroll sideways', async ({
  page,
  checkA11y,
}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Domov' })).toBeVisible();
  await expect(page).toHaveTitle('riso');
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
});

test('a client route is served the shell, and the API is not', async ({ page, request }) => {
  await page.goto('/c/00000000/nothing');
  await expect(page.getByRole('heading', { level: 1, name: 'Stránka sa nenašla' })).toBeVisible();
  const api = await request.get('/api/no/such/route');
  expect(api.status()).toBe(404);
  expect(await api.json()).toEqual({ detail: 'Not Found' });
});

test('the dark theme passes axe too', async ({ page, checkA11y }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', 'dark');
  await checkA11y();
});

test('the seeded admin logs in through the API', async ({ request }) => {
  await request.get('/api/me'); // any response sets the CSRF cookie
  const { cookies } = await request.storageState();
  const csrf = cookies.find((cookie) => cookie.name === 'riso_csrf')?.value ?? '';
  const response = await request.post('/api/auth/login', {
    data: { email: USERS.admin.email, password: SEED_PASSWORD },
    headers: { 'X-CSRF-Token': csrf },
  });
  expect(response.status()).toBe(200);
  const me = (await response.json()) as { customers: { name: string }[] };
  expect(me.customers.map((c) => c.name)).toContain(CUSTOMERS.boldog);
});
