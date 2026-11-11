import type { Page } from '@playwright/test';

import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, type SeededRole } from './pages/login';
import { CUSTOMERS } from './seed';

// Every route of plan §10.1 passes axe, in both themes, for the role that sees it (P2-M7-T07).
// Nothing is changed: each page is opened and read.

/** The customer's ID from the customer switcher's landing (a customer user's Domov). */
async function boldogId(page: Page): Promise<string> {
  const response = await page.request.get('/api/me');
  const me = (await response.json()) as { customers: { id: string; name: string }[] };
  const found = me.customers.find((c) => c.name === CUSTOMERS.boldog);
  if (!found) throw new Error('Boldog is not among the caller’s customers');
  return found.id;
}

async function firstInvoiceId(page: Page, customerId: string): Promise<string> {
  const response = await page.request.get(`/api/customers/${customerId}/invoices?size=1`);
  const body = (await response.json()) as { items: { id: string }[] };
  const found = body.items[0];
  if (!found) throw new Error('no invoice');
  return found.id;
}

interface Route {
  path: (ids: { customer: string; invoice: string }) => string;
  heading: string | RegExp;
}

const CUSTOMER_ROUTES: Route[] = [
  { path: (i) => `/c/${i.customer}`, heading: 'Domov' },
  { path: (i) => `/c/${i.customer}/invoices`, heading: 'Faktúry' },
  { path: (i) => `/c/${i.customer}/invoices/${i.invoice}`, heading: /^Faktúra/ },
  { path: (i) => `/c/${i.customer}/codelists`, heading: 'Číselníky' },
  { path: (i) => `/c/${i.customer}/exchange`, heading: 'Importy a exporty' },
  { path: (i) => `/c/${i.customer}/files`, heading: 'Úložisko' },
  { path: (i) => `/c/${i.customer}/system`, heading: 'Systém' },
];

const ROUTES: Record<SeededRole, Route[]> = {
  viewer: [
    ...CUSTOMER_ROUTES,
    { path: () => '/messages', heading: 'Správy' },
    { path: () => '/profile', heading: 'Profil' },
    { path: () => '/help', heading: 'Pomocník' },
  ],
  user: [
    { path: (i) => `/c/${i.customer}/invoices/new`, heading: 'Nová faktúra' },
    { path: (i) => `/c/${i.customer}/exchange/import`, heading: /import/i },
  ],
  staff: [
    { path: () => '/provider', heading: 'Prehľad klientov' },
    { path: () => '/users', heading: 'Používatelia' },
    { path: () => '/users/new', heading: 'Nový klient' },
  ],
  admin: [
    { path: () => '/admin', heading: 'Platforma' },
    { path: () => '/admin/providers', heading: 'Servisné účty' },
    { path: () => '/admin/codelists', heading: 'Globálne číselníky' },
    { path: () => '/admin/codelists/import', heading: /import/i },
    { path: () => '/admin/audit', heading: 'Audit' },
    { path: () => '/admin/jobs', heading: 'Úlohy' },
    { path: () => '/admin/outbox', heading: 'Odoslané e-maily' },
    { path: () => '/admin/eval', heading: 'Vyhodnotenie' },
  ],
};

for (const role of Object.keys(ROUTES) as SeededRole[]) {
  test(`every route of the ${role} passes axe`, async ({ page, checkA11y }) => {
    test.setTimeout(120_000);
    await loginAs(page, role);
    const customer = await boldogId(page);
    const ids = { customer, invoice: await firstInvoiceId(page, customer) };
    for (const route of ROUTES[role]) {
      await page.goto(route.path(ids));
      await expect(page.getByRole('heading', { level: 1, name: route.heading })).toBeVisible();
      await page.waitForLoadState('networkidle');
      await checkA11y();
      expect(await scrollsHorizontally(page), route.path(ids)).toBe(false);
      await page.emulateMedia({ colorScheme: 'dark' });
      await checkA11y();
      await page.emulateMedia({ colorScheme: 'light' });
    }
  });
}
