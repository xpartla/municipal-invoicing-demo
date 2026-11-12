import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import type { Page } from '@playwright/test';

import { expect, test } from './fixtures';
import { copyBoldog } from './pages/customers';
import { loginAs, openNav } from './pages/login';
import { SEED_PASSWORD, USERS } from './seed';

// The phase 2 acceptance journey (plan §13.2; P2-M8-T05, decision 68), at desktop width (the
// other projects ignore this file, playwright.config.ts):
// 1. a provider copies Boldog into a new customer;
// 2. imports a chart of accounts from a CSV with a new mapping and saves the template;
// 3. invites a user, who sets a password from the outbox link;
// 4. the user uploads three synthetic scans and one UBL invoice, confirms the handwritten
//    fields, books one outright, corrects one and enters one by hand (a credit note, which
//    gets no proposal), and books the UBL invoice;
// 5. exports the booked invoices to CSV and marks them paid;
// 6. Domov shows the counts;
// 7. the admin sees the actions in the audit log, impersonates the user, and the banner and
//    the audit entries show it.
// Scans are read through RecordedReader (decision 63), the UBL file from its XML.

// One IČO per attempt: a retry cannot copy under the IČO its first attempt took.
const COPY_ICO = ['99900904', '99900912'];

const REPO = join(import.meta.dirname, '..', '..');
const SCANS = join(REPO, 'testdata', 'ocr', 'samples');
const EINVOICES = join(REPO, 'testdata', 'einvoice', 'samples');
const ZMOS = 'seed-12-zmos-membership.scan.jpg';
const HORNBACH = 'heldout-07-hornbach-kd.scan.jpg';
const METRO = 'heldout-35-metro-credit-note.scan.pdf';
const TELEKOM = 'heldout-19-telekom-phone.ubl.xml';
/** Read through the server's one worker, behind the other specs' jobs. */
const READ = { timeout: 60_000 };

const TYPES: Record<string, string> = {
  active: 'Aktívny',
  passive: 'Pasívny',
  cost: 'Nákladový',
  revenue: 'Výnosový',
};

/** Boldog's chart of accounts as another program might export it: headers no template
 * knows, semicolons, analytic accounts without their leading zeros. The whole chart, so the
 * proposals keep their accounts. */
function chartCsv(): string {
  const bundle = JSON.parse(
    readFileSync(join(REPO, 'data', 'bundles', '00305863', '2026-08.json'), 'utf-8'),
  ) as { accounts: { su: string; au: string; type: string; description: string }[] };
  const rows = bundle.accounts.map(
    (a) => `${a.su};${String(Number(a.au))};${TYPES[a.type] ?? ''};${a.description}`,
  );
  return ['Účet;Analytika;Druh;Text', ...rows].join('\r\n');
}

async function chooseSource(page: Page, field: string, option: string) {
  await page.getByRole('combobox', { name: `Zdroj hodnoty: ${field}` }).click();
  await page.getByRole('option', { name: option, exact: true }).click();
}

async function logout(page: Page) {
  await openNav(page);
  await page.getByRole('button', { name: 'Odhlásiť' }).click();
  await expect(page.getByText('Odhlásenie prebehlo.')).toBeVisible();
}

/** The check step of a scan: the handwritten date and number confirmed. */
async function confirmScan(
  page: Page,
  handwritten: { date: string; number: string },
  fix: { supplier?: string; noDateOfSupply?: boolean } = {},
) {
  await expect(page.getByRole('tab', { name: 'Kontrola údajov', selected: true })).toBeVisible();
  await page.getByLabel('Dátum zaúčtovania (rukou)', { exact: true }).fill(handwritten.date);
  await page.getByLabel('Poradové číslo dokladu (rukou)', { exact: true }).fill(handwritten.number);
  if (fix.supplier) await page.getByRole('textbox', { name: /^Názov/ }).fill(fix.supplier);
  if (fix.noDateOfSupply) {
    await page.getByLabel('Na faktúre nie je, platí dátum vystavenia').check();
  }
  await page.getByRole('button', { name: 'Potvrdiť' }).click();
  await expect(
    page.getByRole('tab', { name: 'Návrh a zaúčtovanie', selected: true }),
  ).toBeVisible();
}

test('the phase 2 acceptance journey', async ({ page }, testInfo) => {
  test.setTimeout(360_000);
  const ico = COPY_ICO[testInfo.retry];
  if (!ico) throw new Error('no IČO for this attempt');
  const customer = `Obec Akceptačná ${String(testInfo.retry + 1)}`;
  const template = `Rozvrh z iného programu (${String(testInfo.retry + 1)})`;
  const email = `akceptacia-${String(Date.now())}@obec.test`;
  const person = 'Mária Akceptačná';

  await test.step('1. the provider copies Boldog into a new customer', async () => {
    await loginAs(page, 'staff');
    await copyBoldog(page, customer, ico, { memory: true });
  });

  await test.step('2. a chart of accounts from a CSV, a new mapping saved as a template', async () => {
    await openNav(page);
    await page
      .getByRole('navigation')
      .getByRole('link', { name: 'Číselníky', exact: true })
      .click();
    await page.getByRole('tab', { name: 'Účtový rozvrh' }).click();
    await page.getByRole('link', { name: 'Importovať' }).click();
    await expect(page.getByRole('combobox', { name: 'Čo importujete' })).toHaveValue(
      'Účtový rozvrh',
    );
    await page.locator('input[type="file"]').setInputFiles({
      name: 'uctovy-rozvrh.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(chartCsv(), 'utf-8'),
    });
    await page.getByRole('button', { name: 'Nahrať a pokračovať' }).click();
    await page.getByRole('button', { name: 'Pokračovať na mapovanie' }).click();
    await expect(page.getByText(/navrhnuté podľa názvov stĺpcov/)).toBeVisible();
    await chooseSource(page, 'SU (syntetický účet)', 'A · Účet');
    await chooseSource(page, 'AU (analytický účet)', 'B · Analytika');
    await chooseSource(page, 'Typ účtu', 'C · Druh');
    await chooseSource(page, 'Popis', 'D · Text');
    await page
      .getByRole('button', { name: 'Upraviť – úpravy hodnoty poľa AU (analytický účet)' })
      .click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('combobox', { name: 'Pridať úpravu' }).click();
    await page.getByRole('option', { name: 'doplniť nulami' }).click();
    await dialog.getByRole('button', { name: 'Pridať' }).click();
    await dialog.getByRole('button', { name: 'Uložiť' }).click();
    await expect(dialog).toBeHidden();
    await page.getByRole('button', { name: 'Spustiť skúšobný import' }).click();
    await expect(page.getByRole('button', { name: 'Importovať' })).toBeEnabled(READ);
    await page.getByRole('button', { name: 'Importovať' }).click();
    await expect(page.getByText('Import je hotový')).toBeVisible(READ);
    await page.getByRole('textbox', { name: 'Názov šablóny' }).fill(template);
    await page.getByRole('button', { name: 'Uložiť šablónu' }).click();
    await expect(page.getByText(`Šablóna ${template} je uložená.`)).toBeVisible();
  });

  await test.step('3. a user invited, who sets a password from the outbox link', async () => {
    await openNav(page);
    await page.getByRole('navigation').getByRole('link', { name: 'Používatelia' }).click();
    const card = page.getByRole('region', { name: customer });
    await card.getByRole('button', { name: 'Pozvať prihlásenie' }).click();
    const invite = page.getByRole('dialog');
    await invite.getByLabel('E-mail').fill(email);
    await invite.getByLabel('Meno a priezvisko').fill(person);
    await invite.getByRole('button', { name: 'Poslať pozvánku' }).click();
    await expect(page.getByText('Pozvánka je odoslaná.')).toBeVisible();
    await logout(page);

    // The mail waits in the outbox (phase 2 sends none); the admin reads its link.
    await loginAs(page, 'admin');
    await page.goto('/admin/outbox');
    await page.getByLabel('Príjemca').fill(email);
    await page
      .getByRole('row')
      .filter({ hasText: email })
      .getByRole('button', { name: `Pozvánka do riso: ${customer}` })
      .click();
    const href = await page
      .getByRole('dialog')
      .getByRole('link', { name: /\/invitation#/ })
      .getAttribute('href');
    await page.keyboard.press('Escape');
    await logout(page);

    await page.goto(href ?? '');
    await expect(page.getByText(`Vitajte, ${person}.`)).toBeVisible();
    await page.getByLabel(/^Nové heslo/).fill(SEED_PASSWORD);
    await page.getByLabel('Heslo znova').fill(SEED_PASSWORD);
    await page.getByRole('button', { name: 'Nastaviť heslo' }).click();
    await expect(page.getByText('Heslo je nastavené. Teraz sa prihláste.')).toBeVisible();
    await page.getByLabel('E-mail').fill(email);
    await page.getByLabel('Heslo', { exact: true }).fill(SEED_PASSWORD);
    await page.getByRole('button', { name: 'Prihlásiť sa' }).click();
    await expect(page.getByText(`Prehľad klienta ${customer}`)).toBeVisible();
  });

  const uploads = page.getByRole('table', { name: 'Nahrané súbory' });
  await test.step('4. three scans and a UBL invoice uploaded and read', async () => {
    await openNav(page);
    await page.getByRole('link', { name: 'Nová faktúra' }).click();
    await page
      .getByLabel('Vybrať súbory')
      .setInputFiles([
        join(SCANS, ZMOS),
        join(SCANS, HORNBACH),
        join(SCANS, METRO),
        join(EINVOICES, TELEKOM),
      ]);
    await expect(uploads.getByText('Na kontrolu', { exact: true })).toHaveCount(4, READ);
    await page.getByRole('button', { name: 'Pokračovať na kontrolu (4)' }).click();
  });

  await test.step('4a. ZMOS: the handwritten fields confirmed, booked outright', async () => {
    await confirmScan(
      page,
      { date: '2026-02-12', number: '31' },
      { supplier: 'Združenie miest a obcí Slovenska', noDateOfSupply: true },
    );
    await page.getByRole('button', { name: 'Prijať', exact: true }).click();
    await expect(page.getByText('Zaúčtované pod číslom FD/031/26.')).toBeVisible();
  });

  await test.step('4b. Hornbach: corrected with a position from the lists', async () => {
    await page.getByRole('button', { name: 'Ďalšia na kontrolu (3)' }).click();
    await confirmScan(page, { date: '2026-08-27', number: '233' });
    await page.getByRole('button', { name: 'Opraviť a prijať' }).click();
    const line = page.getByRole('group', { name: 'Riadok 1' });
    await line.getByRole('combobox', { name: 'Rozpočtová položka' }).fill('633003 41 01 110 000');
    await page.getByRole('option', { name: /^633003 41 01 110 000/ }).click();
    await page.getByLabel('Poznámka k oprave').fill('drobný hmotný majetok');
    await page.getByRole('button', { name: 'Uložiť opravu' }).click();
    await expect(page.getByText('Zaúčtované pod číslom FD/233/26.')).toBeVisible();
  });

  await test.step('4c. Metro: a credit note, no proposal, entered by hand', async () => {
    await page.getByRole('button', { name: 'Ďalšia na kontrolu (2)' }).click();
    await confirmScan(page, { date: '2026-10-06', number: '276' });
    await expect(page.getByRole('heading', { name: 'Ručné zaúčtovanie' })).toBeVisible();
    await page.getByRole('button', { name: 'Zadať ručne' }).click();
    const line = page.getByRole('group', { name: 'Riadok 1' });
    await expect(line.getByLabel('Suma')).toHaveValue('-44,94');
    await line.getByRole('combobox', { name: 'Rozpočtová položka' }).fill('633003 41 01 110 000');
    await page.getByRole('option', { name: /^633003 41 01 110 000/ }).click();
    await expect(line.getByRole('combobox', { name: 'Účet MD' })).not.toHaveValue('');
    await page.getByLabel('Poznámka k oprave').fill('dobropis');
    await page.getByRole('button', { name: 'Uložiť opravu' }).click();
    await expect(page.getByText(/Zaúčtované pod číslom FD\/276\/26\./)).toBeVisible();
  });

  await test.step('4d. Telekom (UBL): the booking date confirmed, booked outright', async () => {
    await page.getByRole('button', { name: 'Ďalšia na kontrolu (1)' }).click();
    await expect(page.getByRole('tab', { name: 'Kontrola údajov', selected: true })).toBeVisible();
    await page.getByLabel('Dátum zaúčtovania', { exact: true }).fill('2026-10-20');
    await expect(page.getByLabel('Poradové číslo dokladu', { exact: true })).toHaveValue('');
    await page.getByRole('button', { name: 'Potvrdiť' }).click();
    await page.getByRole('button', { name: 'Prijať', exact: true }).click();
    await expect(page.getByText(/^Zaúčtované pod číslom FD\/\d{3}\/26\.$/)).toBeVisible();
  });

  await test.step('5. the booked invoices exported to CSV, then marked paid', async () => {
    await openNav(page);
    await page.getByRole('navigation').getByRole('link', { name: 'Faktúry', exact: true }).click();
    await expect(page.getByText('Počet: 4')).toBeVisible();
    const table = page.getByRole('region', { name: 'Tabuľka faktúr' });
    await expect(table.getByText('Zaúčtovaná', { exact: true })).toHaveCount(4);
    await page.getByRole('button', { name: 'Exportovať', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Export faktúr' });
    await expect(dialog.getByText('Zaúčtované faktúry do exportu: 4')).toBeVisible();
    await dialog.getByRole('button', { name: 'Exportovať' }).click();
    await expect(dialog.getByText(/Súbor je pripravený/)).toBeVisible(READ);
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      dialog.getByRole('link', { name: /^Stiahnuť / }).click(),
    ]);
    const csv = readFileSync(await download.path(), 'utf-8');
    for (const number of ['FD/031/26', 'FD/233/26', 'FD/276/26']) expect(csv).toContain(number);
    expect(csv.split('\n')[0]).toContain(';');
    await page.keyboard.press('Escape');
    await expect(table.getByText('Exportovaná', { exact: true })).toHaveCount(4);

    await page.getByRole('checkbox', { name: 'Vybrať všetky faktúry na strane' }).check();
    await page.getByRole('button', { name: 'Označiť ako uhradené' }).click();
    const pay = page.getByRole('dialog');
    await pay.getByRole('button', { name: 'Označiť ako uhradené' }).click();
    await expect(page.getByText('Hotovo: 4 · nepodarilo sa: 0')).toBeVisible();
    await expect(table.getByText('Uhradená', { exact: true })).toHaveCount(4);
  });

  await test.step('6. Domov shows the counts', async () => {
    await openNav(page);
    await page.getByRole('navigation').getByRole('link', { name: 'Domov' }).click();
    const tiles = page.getByRole('list', { name: 'Ukazovatele mesiaca' });
    await expect(tiles.getByRole('link', { name: /Nahrané\s*4/ })).toBeVisible();
    await expect(tiles.getByRole('link', { name: /^Zaúčtované\s*4/ })).toBeVisible();
    await logout(page);
  });

  await test.step('7. the admin finds the actions in the audit, impersonates the user', async () => {
    await loginAs(page, 'admin');
    const me = (await (await page.request.get('/api/me')).json()) as { user: { id: string } };
    await page.goto('/admin/audit');
    // This customer's events: other specs book invoices in the same database.
    await page.getByRole('main').getByRole('combobox', { name: 'Klient' }).click();
    await page.getByRole('option', { name: customer }).click();
    await expect(page).toHaveURL(/customer=/);
    await page.getByRole('textbox', { name: /^Akcia/ }).fill('invoice.');
    await page.getByRole('button', { name: 'Hľadať' }).click();
    const audit = page.getByRole('region', { name: 'Záznamy auditu', exact: true });
    await expect(audit.getByRole('cell', { name: 'invoice.booked' })).toHaveCount(4);
    await expect(audit.getByRole('cell', { name: 'invoice.paid' }).first()).toBeVisible();

    await page.goto('/users');
    await page.getByRole('button', { name: `Akcie: ${person}` }).click();
    await page.getByRole('menuitem', { name: 'Prihlásiť sa ako' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel(/^Dôvod/).fill('akceptácia: kontrola faktúr');
    await dialog.getByRole('button', { name: `Prihlásiť sa ako ${person}` }).click();
    await expect(page.getByText(`Ste prihlásený ako ${person}.`)).toBeVisible();
    await expect(page.getByText('Dôvod: akceptácia: kontrola faktúr')).toBeVisible();

    // A write as the user: it is audited as the user, with the admin as the real actor.
    await page.goto('/profile');
    const personal = page.getByRole('region', { name: 'Osobné údaje' });
    await personal.getByLabel(/E-mail na upozornenia/).fill('akceptacia-posta@obec.test');
    await personal.getByRole('button', { name: 'Uložiť' }).click();
    await expect(page.getByText('Osobné údaje sú uložené.')).toBeVisible();
    await page.getByRole('button', { name: 'Ukončiť' }).click();
    await expect(page.getByText(/Ste prihlásený ako/)).toHaveCount(0);

    await page.goto('/admin/audit');
    await page.getByRole('textbox', { name: /^Akcia/ }).fill('user.profile_updated');
    await page.getByRole('button', { name: 'Hľadať' }).click();
    const row = audit.getByRole('row').filter({ hasText: person }).first();
    await expect(row).toContainText(`v skutočnosti ${USERS.admin.name}`);
    const started = await page.request.get(
      `/api/admin/audit?action=impersonation.&actor_id=${me.user.id}`,
    );
    const actions = ((await started.json()) as { items: { action: string }[] }).items.map(
      (e) => e.action,
    );
    expect(actions).toEqual(
      expect.arrayContaining(['impersonation.started', 'impersonation.ended']),
    );
  });
});
