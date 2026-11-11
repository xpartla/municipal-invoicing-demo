import type { Page } from '@playwright/test';

import { expect, scrollsHorizontally, test } from './fixtures';
import { loginAs, type SeededRole } from './pages/login';
import { CUSTOMERS } from './seed';

// Every route of plan §10.1 passes axe, in both themes, for the role that sees it (P2-M7-T07),
// and its "?" opens its article in the side panel (P2-M8-T01; axe on the first panel of each
// role). Nothing is changed: each page is opened and read.

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
  /** The title of the article its "?" opens. */
  help: string;
}

const START = 'Začíname';
const IMPORTS = 'Číselníky a importy';
const STAFF = 'Klienti, kopírovanie a šablóny';
const PLATFORM = 'Správa platformy';

const CUSTOMER_ROUTES: Route[] = [
  { path: (i) => `/c/${i.customer}`, heading: 'Domov', help: START },
  { path: (i) => `/c/${i.customer}/invoices`, heading: 'Faktúry', help: 'Zoznam faktúr' },
  {
    // A viewer has no check step: the page opens on the proposal.
    path: (i) => `/c/${i.customer}/invoices/${i.invoice}`,
    heading: /^Faktúra/,
    help: 'Ako čítať návrh zaúčtovania',
  },
  { path: (i) => `/c/${i.customer}/codelists`, heading: 'Číselníky', help: IMPORTS },
  { path: (i) => `/c/${i.customer}/exchange`, heading: 'Importy a exporty', help: IMPORTS },
  { path: (i) => `/c/${i.customer}/files`, heading: 'Úložisko', help: START },
  {
    path: (i) => `/c/${i.customer}/system`,
    heading: 'Systém',
    help: 'Systém: parametre, zvyklosti a kontrola znalostí',
  },
];

const ROUTES: Record<SeededRole, Route[]> = {
  viewer: [
    ...CUSTOMER_ROUTES,
    { path: () => '/messages', heading: 'Správy', help: START },
    { path: () => '/profile', heading: 'Profil', help: START },
    { path: () => '/help', heading: 'Pomocník', help: START },
    { path: () => '/help/ako-to-funguje', heading: 'Ako to funguje', help: START },
  ],
  user: [
    {
      path: (i) => `/c/${i.customer}/invoices/new`,
      heading: 'Nová faktúra',
      help: 'Nahrávanie a skenovanie faktúr',
    },
    { path: (i) => `/c/${i.customer}/exchange/import`, heading: /import/i, help: IMPORTS },
  ],
  staff: [
    { path: () => '/provider', heading: 'Prehľad klientov', help: STAFF },
    { path: () => '/users', heading: 'Používatelia', help: STAFF },
    { path: () => '/users/new', heading: 'Nový klient', help: STAFF },
  ],
  admin: [
    { path: () => '/admin', heading: 'Platforma', help: PLATFORM },
    { path: () => '/admin/providers', heading: 'Servisné účty', help: PLATFORM },
    { path: () => '/admin/codelists', heading: 'Globálne číselníky', help: 'Globálne číselníky' },
    { path: () => '/admin/codelists/import', heading: /import/i, help: 'Globálne číselníky' },
    { path: () => '/admin/audit', heading: 'Audit', help: PLATFORM },
    { path: () => '/admin/jobs', heading: 'Úlohy', help: PLATFORM },
    { path: () => '/admin/outbox', heading: 'Odoslané e-maily', help: PLATFORM },
    { path: () => '/admin/eval', heading: 'Vyhodnotenie', help: PLATFORM },
  ],
};

/** Opens the screen's "?", checks the article it shows, and closes the panel again. */
async function openHelp(page: Page, title: string, checkA11y: () => Promise<void> | false) {
  await page.getByRole('button', { name: 'Pomocník k tejto obrazovke' }).click();
  const panel = page.getByRole('dialog', { name: 'Pomocník' });
  await expect(panel.getByRole('heading', { level: 3, name: title, exact: true })).toBeVisible();
  await checkA11y();
  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();
}

for (const role of Object.keys(ROUTES) as SeededRole[]) {
  test(`every route of the ${role} passes axe`, async ({ page, checkA11y }) => {
    test.setTimeout(120_000);
    await loginAs(page, role);
    const customer = await boldogId(page);
    const ids = { customer, invoice: await firstInvoiceId(page, customer) };
    for (const [index, route] of ROUTES[role].entries()) {
      await page.goto(route.path(ids));
      await expect(page.getByRole('heading', { level: 1, name: route.heading })).toBeVisible();
      await page.waitForLoadState('networkidle');
      await checkA11y();
      expect(await scrollsHorizontally(page), route.path(ids)).toBe(false);
      await page.emulateMedia({ colorScheme: 'dark' });
      await checkA11y();
      await page.emulateMedia({ colorScheme: 'light' });
      await openHelp(page, route.help, () => index === 0 && checkA11y());
    }
  });
}
