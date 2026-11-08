import type { Page } from '@playwright/test';

import { expect, test } from './fixtures';
import { loginAs, openNav, type SeededRole } from './pages/login';
import { CUSTOMERS, SEED_PASSWORD, USERS } from './seed';

// The journeys of P2-M1 (plan §14 exit criterion: every role logs in and sees its navbar;
// impersonation is audited). The specs share one seeded database and run in parallel at three
// widths, so the ones that write use addresses of their own and fields nobody else checks.

const CUSTOMER_ITEMS = ['Domov', 'Faktúry', 'Číselníky', 'Importy a exporty', 'Úložisko', 'Systém'];
const BOTTOM = ['Pomocník', 'Profil', 'Pôvodná ukážka'];

const NAVBAR: Record<SeededRole, string[]> = {
  viewer: [...CUSTOMER_ITEMS, 'Správy', ...BOTTOM],
  user: [...CUSTOMER_ITEMS, 'Správy', ...BOTTOM],
  staff: ['Správy', 'Prehľad klientov', 'Používatelia', ...BOTTOM],
  admin: [
    'Správy',
    'Prehľad klientov',
    'Používatelia',
    'Platforma',
    'Servisné účty',
    'Globálne číselníky',
    'Audit',
    'Úlohy',
    'Odoslané e-maily',
    'Vyhodnotenie',
    ...BOTTOM,
  ],
};

async function navbarItems(page: Page): Promise<string[]> {
  await openNav(page);
  const nav = page.getByRole('navigation', { name: 'Hlavné menu' });
  return nav
    .getByRole('link')
    .evaluateAll((links) =>
      links.map((link) => (link.getAttribute('aria-label') ?? link.textContent).trim()),
    );
}

function unique(prefix: string): string {
  return `${prefix}.${String(Date.now())}.${String(Math.floor(Math.random() * 1e6))}@lehota.test`;
}

test.describe('1. each role sees exactly its navbar', () => {
  for (const role of Object.keys(NAVBAR) as SeededRole[]) {
    test(role, async ({ page }) => {
      await loginAs(page, role);
      expect(await navbarItems(page)).toEqual(NAVBAR[role]);
      await expect(page.getByRole('button', { name: 'Odhlásiť' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Nová faktúra' })).toBeDisabled();
    });
  }
});

test('2. an admin invites a user, who sets a password from the outbox link and logs in', async ({
  page,
}) => {
  const email = unique('nova');
  await loginAs(page, 'admin');
  await page.goto('/users');
  const lehota = page.getByRole('region', { name: CUSTOMERS.second });
  await lehota.getByRole('button', { name: 'Pozvať prihlásenie' }).click();
  const invite = page.getByRole('dialog');
  await invite.getByLabel('E-mail').fill(email);
  await invite.getByLabel('Meno a priezvisko').fill('Nová Používateľka');
  await invite.getByRole('button', { name: 'Poslať pozvánku' }).click();
  await expect(page.getByText('Pozvánka je odoslaná.')).toBeVisible();
  await expect(lehota.getByText(email)).toBeVisible();

  await page.goto('/admin/outbox');
  await page.getByLabel('Príjemca').fill(email);
  await page
    .getByRole('row')
    .filter({ hasText: email })
    .getByRole('button', { name: `Pozvánka do riso: ${CUSTOMERS.second}` })
    .click();
  const link = page.getByRole('dialog').getByRole('link', { name: /\/invitation#/ });
  const href = await link.getAttribute('href');
  expect(href).toMatch(/\/invitation#[A-Za-z0-9_-]+$/);

  await page.keyboard.press('Escape');
  await openNav(page);
  await page.getByRole('button', { name: 'Odhlásiť' }).click();
  await expect(page.getByText('Odhlásenie prebehlo.')).toBeVisible();

  await page.goto(href ?? '');
  await expect(page.getByText('Vitajte, Nová Používateľka.')).toBeVisible();
  await page.getByLabel(/^Nové heslo/).fill(SEED_PASSWORD);
  await page.getByLabel('Heslo znova').fill(SEED_PASSWORD);
  await page.getByRole('button', { name: 'Nastaviť heslo' }).click();
  await expect(page.getByText('Heslo je nastavené. Teraz sa prihláste.')).toBeVisible();

  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Heslo', { exact: true }).fill(SEED_PASSWORD);
  await page.getByRole('button', { name: 'Prihlásiť sa' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Domov' })).toBeVisible();
  await expect(page.getByText(`Prehľad klienta ${CUSTOMERS.second}`)).toBeVisible();
});

test('3. staff switch between two customers', async ({ page }) => {
  await loginAs(page, 'staff');
  await expect(page).toHaveURL(/\/users$/);
  await openNav(page);
  const switcher = page.getByRole('navigation').getByLabel('Klient', { exact: true });
  await switcher.click();
  await page.getByRole('option', { name: CUSTOMERS.boldog }).click();
  await expect(page.getByText(`Prehľad klienta ${CUSTOMERS.boldog}`)).toBeVisible();
  const boldog = page.url();

  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Faktúry' }).click();
  await expect(page).toHaveURL(/\/invoices$/);
  await openNav(page);
  await switcher.click();
  await page.getByRole('option', { name: CUSTOMERS.second }).click();
  await expect(page).toHaveURL(/\/invoices$/);
  expect(page.url()).not.toBe(`${boldog}/invoices`);
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Domov' }).click();
  await expect(page.getByText(`Prehľad klienta ${CUSTOMERS.second}`)).toBeVisible();
  await openNav(page);
  await expect(switcher).toHaveValue(CUSTOMERS.second);
});

test('4. an admin impersonates the Boldog user, a profile change is audited with both IDs', async ({
  page,
}) => {
  await loginAs(page, 'admin');
  const admin = (await (await page.request.get('/api/me')).json()) as { user: { id: string } };
  await page.goto('/users');
  await page
    .getByRole('button', { name: `Akcie: ${USERS.user.name}` })
    .first()
    .click();
  await page.getByRole('menuitem', { name: 'Prihlásiť sa ako' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel(/^Dôvod/).fill('E2E: overenie profilu');
  await dialog.getByRole('button', { name: `Prihlásiť sa ako ${USERS.user.name}` }).click();

  await expect(page.getByText(`Ste prihlásený ako ${USERS.user.name}.`)).toBeVisible();
  await expect(page.getByText('Dôvod: E2E: overenie profilu')).toBeVisible();
  const jana = (await (await page.request.get('/api/me')).json()) as { user: { id: string } };

  await page.goto('/profile');
  await expect(page.getByText(/nemožno meniť jeho heslo/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Zmeniť heslo' })).toBeDisabled();
  const personal = page.getByRole('region', { name: 'Osobné údaje' });
  await personal.getByLabel(/E-mail na upozornenia/).fill(unique('posta'));
  await personal.getByRole('button', { name: 'Uložiť' }).click();
  await expect(page.getByText('Osobné údaje sú uložené.')).toBeVisible();

  await page.getByRole('button', { name: 'Ukončiť' }).click();
  await expect(page).toHaveURL(/\/users$/);
  await expect(page.getByText(/Ste prihlásený ako/)).toHaveCount(0);

  const audit = await page.request.get(
    `/api/admin/audit?action=user.profile_updated&actor_id=${jana.user.id}`,
  );
  const events = ((await audit.json()) as { items: Record<string, unknown>[] }).items;
  expect(events.some((e) => e.actor_id === jana.user.id && e.real_actor_id === admin.user.id)).toBe(
    true,
  );
  const started = await page.request.get(
    `/api/admin/audit?action=impersonation.&actor_id=${admin.user.id}`,
  );
  const actions = ((await started.json()) as { items: { action: string }[] }).items.map(
    (e) => e.action,
  );
  expect(actions).toEqual(expect.arrayContaining(['impersonation.started', 'impersonation.ended']));
});

test('5. a viewer sees no write buttons', async ({ page }) => {
  await loginAs(page, 'viewer');
  await expect(page.getByRole('heading', { level: 1, name: 'Domov' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Nová faktúra' })).toBeDisabled();

  await page.goto('/profile');
  const customer = page.getByRole('region', { name: 'Údaje klienta' });
  await expect(customer.getByText('Údaje klienta môžete iba prezerať.')).toBeVisible();
  await expect(customer.getByRole('button')).toHaveCount(0);
  await expect(customer.getByLabel('Ulica a číslo')).toHaveAttribute('readonly');

  await page.goto('/users');
  await expect(page.getByRole('heading', { level: 1, name: 'Prístup zamietnutý' })).toBeVisible();
});
