import type { Page } from '@playwright/test';

import { expect, test } from './fixtures';
import { loginAs, openNav } from './pages/login';
import { CUSTOMERS } from './seed';

// The journeys of P2-M3 (plan §13.2). The three widths run in parallel on one seeded
// database, so a journey that writes uses data of its own per width: journey 1 imports into
// a customer it creates, journey 3 copies Boldog under an IČO and a login of its own.

const WIDTH: Record<string, { importIco: string; copyIco: string }> = {
  phone: { importIco: '99900076', copyIco: '99900033' },
  tablet: { importIco: '99900084', copyIco: '99900041' },
  desktop: { importIco: '99900092', copyIco: '99900068' },
};

function width(name: string) {
  const found = WIDTH[name];
  if (!found) throw new Error(`no data for the width ${name}`);
  return found;
}

/** A chart of accounts as an accounting program might export it: headers no template knows,
 * analytic accounts without their leading zeros. */
function chart(label: string): string {
  return [
    'Účet;Analytika;Druh;Text',
    `518;1;Nákladový;Telefóny ${label}`,
    `518;3;Nákladový;Internet ${label}`,
    `321;0;Pasívny;Dodávatelia ${label}`,
  ].join('\r\n');
}

async function upload(page: Page, name: string, content: string) {
  await page.locator('input[type="file"]').setInputFiles({
    name,
    mimeType: 'text/csv',
    buffer: Buffer.from(content, 'utf-8'),
  });
  await page.getByRole('button', { name: 'Nahrať a pokračovať' }).click();
  await expect(page.getByRole('region', { name: 'Ukážka súboru' })).toBeVisible();
  await page.getByRole('button', { name: 'Pokračovať na mapovanie' }).click();
  await expect(page.getByRole('region', { name: 'Mapovanie polí' })).toBeVisible();
}

async function chooseSource(page: Page, field: string, option: string) {
  await page.getByRole('combobox', { name: `Zdroj hodnoty: ${field}` }).click();
  await page.getByRole('option', { name: option, exact: true }).click();
}

test('1. importing a CSV chart of accounts with a new mapping, saved as a template', async ({
  page,
}, testInfo) => {
  const { importIco } = width(testInfo.project.name);
  const customer = `Obec Import ${testInfo.project.name}`;
  const template = `Rozvrh z CSV (${testInfo.project.name})`;
  await loginAs(page, 'admin');

  // An empty customer of its own, so the parallel widths do not change each other's lists.
  await page.goto('/users/new');
  await page.getByRole('button', { name: 'Ďalej' }).click();
  await page.getByRole('textbox', { name: /^Názov/ }).fill(customer);
  await page.getByRole('textbox', { name: /^IČO/ }).fill(importIco);
  await page.getByRole('button', { name: 'Ďalej' }).click();
  await page.getByRole('button', { name: 'Vytvoriť klienta' }).click();
  await expect(page.getByText(`Klient ${customer} je vytvorený`)).toBeVisible();
  await page.getByRole('link', { name: 'Otvoriť klienta' }).click();
  await expect(page.getByText(`Prehľad klienta ${customer}`)).toBeVisible();

  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Číselníky', exact: true }).click();
  await page.getByRole('tab', { name: 'Účtový rozvrh' }).click();
  await expect(page.getByText(/tento číselník ešte nie je/)).toBeVisible();
  await page.getByRole('link', { name: 'Importovať' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Nový import' })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Čo importujete' })).toHaveValue('Účtový rozvrh');
  await upload(page, 'rozvrh.csv', chart(testInfo.project.name));

  // A new mapping: no template knows these headers; choose each column, pad AU with zeros.
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
  await expect(page.getByRole('row', { name: /^AU \(analytický účet\)/ })).toContainText(
    'doplniť nulami na 3',
  );

  await page.getByRole('button', { name: 'Spustiť skúšobný import' }).click();
  await expect(page.getByText('Bez chýb.')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/import vytvorí jeho prvú verziu/)).toBeVisible();
  await page.getByRole('button', { name: 'Importovať' }).click();
  // The import is a job: it may wait behind the other widths' uploads in the one worker.
  await expect(page.getByText('Import je hotový')).toBeVisible({ timeout: 60_000 });

  await page.getByRole('textbox', { name: 'Názov šablóny' }).fill(template);
  await page.getByRole('button', { name: 'Uložiť šablónu' }).click();
  await expect(page.getByText(`Šablóna ${template} je uložená.`)).toBeVisible();

  // The new version on Číselníky, with its rows and its origin.
  await page.getByRole('main').getByRole('link', { name: 'Číselníky', exact: true }).click();
  await page.getByRole('tab', { name: 'Účtový rozvrh' }).click();
  const accounts = page.getByRole('region', { name: 'Účtový rozvrh' });
  await expect(accounts.getByText(`Telefóny ${testInfo.project.name}`)).toBeVisible();
  await expect(accounts.getByRole('cell', { name: '003', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Verzie a zmeny' }).click();
  const versions = page.getByRole('dialog').getByRole('region', { name: 'Verzie' });
  await expect(versions.getByRole('row')).toHaveCount(2); // header, version 1
  await expect(versions.getByRole('cell', { name: 'import', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');

  // The next file with these headers gets the template.
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Importy a exporty' }).click();
  await page.getByRole('link', { name: 'Nový import' }).click();
  await upload(page, 'rozvrh-2.csv', chart('znova'));
  await expect(page.getByText(template)).toBeVisible();
  await page.getByRole('button', { name: 'Zrušiť import' }).click();
  await expect(page.getByText('Import je zrušený.')).toBeVisible();
});

test('2. a failing import cannot be confirmed', async ({ page }) => {
  await loginAs(page, 'user');
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Importy a exporty' }).click();
  await page.getByRole('link', { name: 'Nový import' }).click();
  await upload(
    page,
    'zly-rozvrh.csv',
    ['SU;AU;Typ účtu;Popis', '518;001;Nákladový;Telefóny', '5x8;002;Nákladový;Zlý účet'].join(
      '\r\n',
    ),
  );
  await page.getByRole('button', { name: 'Spustiť skúšobný import' }).click();
  const errors = page.getByRole('region', { name: 'Chyby skúšobného importu' });
  await expect(errors).toBeVisible({ timeout: 60_000 });
  await expect(errors.getByRole('cell', { name: '3', exact: true })).toBeVisible();
  await expect(page.getByText('Import sa nedá potvrdiť')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Importovať' })).toBeDisabled();
  await expect(page.getByRole('checkbox', { name: /Importovať napriek/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Zrušiť import' }).click();
  await expect(page.getByText('Import je zrušený.')).toBeVisible();
});

test('3. staff copy Boldog into a new customer and invite its login', async ({
  page,
}, testInfo) => {
  const { copyIco } = width(testInfo.project.name);
  const customer = `Obec Kópia ${testInfo.project.name}`;
  const email = `starosta.${testInfo.project.name}@kopia.test`;
  await loginAs(page, 'staff');
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Používatelia' }).click();
  await page.getByRole('link', { name: 'Nový klient' }).click();

  await page.getByRole('radio', { name: /Kópia jedného z vašich klientov/ }).check();
  await page.getByRole('combobox', { name: 'Kopírovať z klienta' }).click();
  await page.getByRole('option', { name: new RegExp(CUSTOMERS.boldog) }).click();
  await page.getByRole('button', { name: 'Ďalej' }).click();
  await page.getByRole('textbox', { name: /^Názov/ }).fill(customer);
  await page.getByRole('textbox', { name: /^IČO/ }).fill(copyIco);
  await page.getByRole('button', { name: 'Ďalej' }).click();
  await expect(page.getByRole('checkbox', { name: 'Číselníky (aktívne verzie)' })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'Pamäť dodávateľov' })).not.toBeChecked();
  await page.getByRole('button', { name: 'Ďalej' }).click();
  await page.getByRole('checkbox', { name: 'Pozvať prvé prihlásenie' }).check();
  await page.getByRole('textbox', { name: 'E-mail' }).fill(email);
  await page.getByRole('textbox', { name: 'Meno a priezvisko' }).fill('Starosta Kópie');
  await page.getByRole('button', { name: 'Vytvoriť kópiu' }).click();

  await expect(page.getByText(`Klient ${customer} je vytvorený`)).toBeVisible();
  await expect(page.getByText(/^Hotovo: skopírovaných číselníkov [1-9]/)).toBeVisible({
    timeout: 60_000,
  });

  // The copy's lists are its own new versions.
  await page.getByRole('link', { name: 'Otvoriť klienta' }).click();
  await expect(page.getByText(`Prehľad klienta ${customer}`)).toBeVisible();
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Číselníky', exact: true }).click();
  const expense = page.getByRole('region', { name: 'Výdavkový rozpočet' });
  await expect(expense.getByRole('cell', { name: '611000' }).first()).toBeVisible();
  await page.getByLabel('Hľadať').fill('telefon');
  await expect(expense.getByRole('cell', { name: '632005' }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Verzie a zmeny' }).click();
  const versions = page.getByRole('dialog').getByRole('region', { name: 'Verzie' });
  await expect(versions.getByRole('row')).toHaveCount(2);
  await expect(versions.getByRole('cell', { name: 'kópia', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');

  // The invited login waits under the new customer on Používatelia.
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Používatelia' }).click();
  const card = page.getByRole('region', { name: customer });
  await expect(card.getByText(email)).toBeVisible();
});
