import { join } from 'node:path';

import type { Page } from '@playwright/test';

import { expect, scrollsHorizontally, test } from './fixtures';
import { copyBoldog } from './pages/customers';
import { loginAs, openNav } from './pages/login';

// The M6 journey (P2-M6-T07, plan §13.2): a UBL invoice and an ISDOC PDF uploaded at once,
// read from their XML without OCR; the check step with the e-invoice viewer (the rendered
// invoice, the PDF's page, the raw XML; axe in both themes, each width); the booking date
// confirmed as the upload date and the number left to the booking (decision 65); both booked.
// Each width works in a copy of Boldog of its own, under its own IČO, since a file is
// uploaded once per customer.

// One IČO per width and attempt: a retry cannot copy under the IČO its first attempt took.
const COPY_ICO: Record<string, readonly string[]> = {
  phone: ['99900505', '99900513'],
  tablet: ['99900521', '99900530'],
  desktop: ['99900548', '99900556'],
};

const SAMPLES = join(import.meta.dirname, '..', '..', 'testdata', 'einvoice', 'samples');
const UBL = 'heldout-07-hornbach-kd.ubl.xml';
const ISDOC_PDF = 'seed-04-fcc-waste.isdoc.pdf';
/** Read through the server's one worker, behind the other widths' jobs. */
const READ = { timeout: 60_000 };

/** The check step of an e-invoice: the upload date taken for the booking date, the number
 * left empty, "Potvrdiť"; then booked as proposed. Without a number asked for, the booking
 * places the invoice by its date of supply (decision 61): one supplied before a booked one
 * takes its number and moves it up, which the booking dialog shows first. */
async function confirmAndBook(page: Page, number: string, moves?: [string, string]) {
  await expect(page.getByRole('tab', { name: 'Kontrola údajov', selected: true })).toBeVisible();
  const date = page.getByLabel('Dátum zaúčtovania', { exact: true });
  await expect(page.getByRole('button', { name: /· deň nahratia$/ })).toBeVisible();
  await date.focus();
  await page.keyboard.press('Enter');
  await expect(date).not.toHaveValue('');
  await expect(page.getByLabel('Poradové číslo dokladu', { exact: true })).toHaveValue('');
  await page.getByRole('button', { name: 'Potvrdiť' }).click();
  await expect(
    page.getByRole('tab', { name: 'Návrh a zaúčtovanie', selected: true }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Zaúčtovanie záväzku' })).toBeVisible();
  await page.getByRole('button', { name: 'Prijať', exact: true }).click();
  if (moves) {
    const dialog = page.getByRole('dialog', { name: 'Zaúčtovanie' });
    await expect(dialog.getByText(`Doklad dostane číslo ${number}.`)).toBeVisible();
    const moved = dialog.getByRole('listitem');
    await expect(moved).toHaveCount(1);
    await expect(moved).toContainText(moves[0]);
    await expect(moved).toContainText(moves[1]);
    await dialog.getByRole('button', { name: 'Zaúčtovať' }).click();
  }
  await expect(page.getByRole('heading', { level: 1, name: `Faktúra ${number}` })).toBeVisible();
}

test('a UBL invoice and an ISDOC PDF read, checked and booked', async ({
  page,
  checkA11y,
}, testInfo) => {
  test.setTimeout(240_000);
  const ico = COPY_ICO[testInfo.project.name]?.[testInfo.retry];
  if (!ico) throw new Error(`no IČO for the width ${testInfo.project.name}`);
  await loginAs(page, 'staff');
  const name = `Obec E-faktúry ${testInfo.project.name} ${String(testInfo.retry + 1)}`;
  await copyBoldog(page, name, ico, { memory: true });

  await test.step('both files uploaded at once and read', async () => {
    await openNav(page);
    await page.getByRole('link', { name: 'Nová faktúra' }).click();
    await expect(page.getByRole('region', { name: 'Nahrávanie faktúr' })).toBeVisible();
    await page
      .getByLabel('Vybrať súbory')
      .setInputFiles([UBL, ISDOC_PDF].map((file) => join(SAMPLES, file)));
    const uploads = page.getByRole('table', { name: 'Nahrané súbory' });
    await expect(uploads.getByText('Na kontrolu', { exact: true })).toHaveCount(2, READ);
    await page.getByRole('button', { name: 'Pokračovať na kontrolu (2)' }).click();
  });

  await test.step('the UBL invoice in the viewer passes axe and fits', async () => {
    const viewer = page.getByRole('region', { name: 'Elektronická faktúra' });
    await expect(viewer.getByText('UBL 2.1 (Peppol)')).toBeVisible();
    await expect(viewer.getByRole('heading', { name: /^Faktúra 2026-418-019944/ })).toBeVisible();
    await expect(
      page.getByText('Údaje z elektronickej faktúry, ako ich poslal dodávateľ.'),
    ).toBeVisible();
    // No note: no crop; the number's hint tells what the booking will do.
    await expect(page.getByRole('img', { name: /Rukou písaná poznámka/ })).toHaveCount(0);
    await expect(
      page.getByLabel('Poradové číslo dokladu', { exact: true }),
    ).toHaveAccessibleDescription(/pridelí zaúčtovanie podľa dátumu dodania/);
    // The focused field is marked in the rendered invoice.
    await page.getByLabel('IČO').focus();
    await expect(viewer.locator('[data-field="supplier.ico"][data-focused="true"]')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await checkA11y();
    expect(await scrollsHorizontally(page)).toBe(false);
    await page.emulateMedia({ colorScheme: 'dark' });
    await checkA11y();
    await page.emulateMedia({ colorScheme: 'light' });
    // The raw XML, as text.
    await viewer.getByRole('tab', { name: 'XML' }).click();
    await expect(viewer.getByRole('region', { name: 'Obsah súboru XML' })).toContainText(
      '<cbc:ID>2026-418-019944</cbc:ID>',
    );
    await checkA11y();
    expect(await scrollsHorizontally(page)).toBe(false);
    await viewer.getByRole('tab', { name: 'Faktúra' }).click();
  });

  await test.step('the UBL invoice: the upload date confirmed, booked by its date of supply', async () => {
    await confirmAndBook(page, 'FD/001/26');
  });

  await test.step('the ISDOC PDF: its page and its invoice, then booked before the first', async () => {
    await page.getByRole('button', { name: 'Ďalšia na kontrolu (1)' }).click();
    const viewer = page.getByRole('region', { name: 'Elektronická faktúra' });
    await expect(viewer.getByText('ISDOC 6.0.2')).toBeVisible();
    await expect(viewer.getByText(/^Príloha PDF: .+\.isdoc$/)).toBeVisible();
    await viewer.getByRole('tab', { name: 'PDF' }).click();
    const image = viewer.getByRole('img', { name: 'Strana 1 dokladu' });
    await expect(image).toBeVisible();
    await expect
      .poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth))
      .toBeGreaterThan(0);
    await page.waitForLoadState('networkidle');
    await checkA11y();
    expect(await scrollsHorizontally(page)).toBe(false);
    // Supplied before the UBL invoice: it takes FD/001/26, which moves up to FD/002/26.
    await confirmAndBook(page, 'FD/001/26', ['FD/001/26', 'FD/002/26']);
  });

  await test.step('Faktúry lists both, booked, as e-invoices', async () => {
    await openNav(page);
    await page.getByRole('navigation').getByRole('link', { name: 'Faktúry', exact: true }).click();
    await expect(page.getByText('Počet: 2')).toBeVisible();
    const table = page.getByRole('region', { name: 'Tabuľka faktúr' });
    await expect(table.getByText('Zaúčtovaná', { exact: true })).toHaveCount(2);
  });
});
