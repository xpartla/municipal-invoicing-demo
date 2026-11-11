import { join } from 'node:path';

import type { Page } from '@playwright/test';

import { expect, scrollsHorizontally, test } from './fixtures';
import { copyBoldog } from './pages/customers';
import { loginAs, openNav } from './pages/login';

// The M5 journeys (P2-M5-T12, plan §13.2): three scans uploaded, read through RecordedReader
// (plan §2 decision 63), checked with the document viewer (axe in both themes, each width;
// P2-M5-T10), one booked as proposed and one corrected; a duplicate refused with its link; a
// file that cannot be read, read again and entered by hand; Úložisko listing the files
// (T11). The widths run in parallel on one seeded database and a file can be uploaded once
// per customer, so each width works in a copy of Boldog of its own (with the supplier memory,
// under its own IČO). One copy serves all the journeys: the server's one worker reads every
// upload and makes every copy in turn.

// One IČO per width and attempt: a retry cannot copy under the IČO its first attempt took.
const COPY_ICO: Record<string, readonly string[]> = {
  phone: ['99900301', '99900319'],
  tablet: ['99900327', '99900335'],
  desktop: ['99900343', '99900351'],
};

const SAMPLES = join(import.meta.dirname, '..', '..', 'testdata', 'ocr', 'samples');
const ZMOS = 'seed-12-zmos-membership.scan.jpg';
const HORNBACH = 'heldout-07-hornbach-kd.scan.jpg';
const ZSE = 'heldout-23-zse-ocu-ms.scan.jpg';
/** Read through the server's one worker, behind the other widths' jobs. */
const READ = { timeout: 60_000 };

async function openUpload(page: Page) {
  await openNav(page);
  await page.getByRole('link', { name: 'Nová faktúra' }).click();
  await expect(page.getByRole('region', { name: 'Nahrávanie faktúr' })).toBeVisible();
}

/** The check step: the handwritten date and number confirmed, the fields as given. */
async function confirmFields(
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
  await expect(page.getByRole('heading', { name: 'Zaúčtovanie záväzku' })).toBeVisible();
}

test('scans uploaded, checked and booked; a duplicate refused; an unreadable file entered by hand', async ({
  page,
  checkA11y,
}, testInfo) => {
  test.setTimeout(240_000);
  const ico = COPY_ICO[testInfo.project.name]?.[testInfo.retry];
  if (!ico) throw new Error(`no IČO for the width ${testInfo.project.name}`);
  await loginAs(page, 'staff');
  const name = `Obec Skeny ${testInfo.project.name} ${String(testInfo.retry + 1)}`;
  await copyBoldog(page, name, ico, { memory: true });
  const uploads = page.getByRole('table', { name: 'Nahrané súbory' });

  await test.step('three scans at once, each read, then checked in order', async () => {
    await openUpload(page);
    await page
      .getByLabel('Vybrať súbory')
      .setInputFiles([ZMOS, HORNBACH, ZSE].map((file) => join(SAMPLES, file)));
    await expect(uploads.getByText('Na kontrolu', { exact: true })).toHaveCount(3, READ);
    await page.getByRole('button', { name: 'Pokračovať na kontrolu (3)' }).click();
  });

  await test.step('the check step with the document viewer passes axe and fits', async () => {
    await expect(page.getByRole('tab', { name: 'Kontrola údajov', selected: true })).toBeVisible();
    const viewer = page.getByRole('region', { name: 'Doklad' });
    const image = viewer.getByRole('img', { name: 'Strana 1 dokladu' });
    await expect(image).toBeVisible();
    await expect
      .poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth))
      .toBeGreaterThan(0);
    await expect(page.getByRole('img', { name: /Rukou písaná poznámka/ })).toBeVisible();
    await expect(page.getByRole('group', { name: /Návrhy pre Poradové číslo/ })).toBeVisible();
    // A field's focus shows its box on the document.
    await page.getByLabel('IČO').focus();
    await expect(viewer.getByTestId('viewer-highlight')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await checkA11y();
    expect(await scrollsHorizontally(page)).toBe(false);
    await page.emulateMedia({ colorScheme: 'dark' });
    await checkA11y();
    await page.emulateMedia({ colorScheme: 'light' });
    // Zoomed in, the page pans inside the viewer, not the page.
    await viewer.getByRole('button', { name: 'Priblížiť' }).click();
    await expect(viewer.getByText('150 %')).toBeVisible();
    expect(await scrollsHorizontally(page)).toBe(false);
  });

  await test.step('ZMOS: its name misread, no date of supply; booked as proposed', async () => {
    await confirmFields(
      page,
      { date: '2026-02-12', number: '31' },
      { supplier: 'Združenie miest a obcí Slovenska', noDateOfSupply: true },
    );
    await page.getByRole('button', { name: 'Prijať', exact: true }).click();
    await expect(page.getByText('Zaúčtované pod číslom FD/031/26.')).toBeVisible();
    await expect(page.getByRole('heading', { level: 1, name: 'Faktúra FD/031/26' })).toBeVisible();
  });

  await test.step('Hornbach: checked, corrected with a position from the lists', async () => {
    await page.getByRole('button', { name: 'Ďalšia na kontrolu (2)' }).click();
    await confirmFields(page, { date: '2026-08-27', number: '233' });
    await page.getByRole('button', { name: 'Opraviť a prijať' }).click();
    const line = page.getByRole('group', { name: 'Riadok 1' });
    await line.getByRole('combobox', { name: 'Rozpočtová položka' }).fill('633003 41 01 110 000');
    await page.getByRole('option', { name: /^633003 41 01 110 000/ }).click();
    await expect(line.getByRole('combobox', { name: 'Účet MD' })).toHaveValue(/^501 000/);
    await page.getByLabel('Poznámka k oprave').fill('drobný hmotný majetok');
    await page.getByRole('button', { name: 'Uložiť opravu' }).click();
    await expect(page.getByText('Zaúčtované pod číslom FD/233/26.')).toBeVisible();
  });

  await test.step('ZSE: the name read from the wrong line, corrected; left proposed', async () => {
    await page.getByRole('button', { name: 'Ďalšia na kontrolu (1)' }).click();
    await confirmFields(
      page,
      { date: '2026-09-23', number: '258' },
      { supplier: 'Západoslovenská energetika, a.s.' },
    );
    await expect(page.getByRole('button', { name: /Ďalšia na kontrolu/ })).toBeHidden();
    await openNav(page);
    await page.getByRole('navigation').getByRole('link', { name: 'Faktúry', exact: true }).click();
    await expect(page.getByText('Počet: 3')).toBeVisible();
    const table = page.getByRole('region', { name: 'Tabuľka faktúr' });
    await expect(table.getByText('Zaúčtovaná', { exact: true })).toHaveCount(2);
  });

  await test.step('the same file again is refused, linking its invoice', async () => {
    await openUpload(page);
    await page.getByLabel('Vybrať súbory').setInputFiles(join(SAMPLES, HORNBACH));
    await expect(uploads.getByText('Rovnaký súbor už bol nahraný.')).toBeVisible();
    await expect(uploads.getByText('Odmietnutý', { exact: true })).toBeVisible();
    await uploads.getByRole('link', { name: 'Otvoriť faktúru z rovnakého súboru' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Faktúra FD/233/26' })).toBeVisible();
  });

  await test.step('a damaged file is not read, read again, then entered by hand', async () => {
    // A JPEG by its first bytes, damaged after them: accepted, then not read.
    await openUpload(page);
    const damaged = Buffer.concat([
      Buffer.from([0xff, 0xd8, 0xff, 0xe0]),
      Buffer.from('poškodený súbor '.repeat(64)),
    ]);
    await page
      .getByLabel('Vybrať súbory')
      .setInputFiles({ name: 'faktura-telekom.jpg', mimeType: 'image/jpeg', buffer: damaged });
    await expect(uploads.getByText('Súbor sa nedá otvoriť.')).toBeVisible(READ);
    await expect(uploads.getByText('Neprečítaný', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Pokračovať na kontrolu (0)' })).toBeDisabled();
    await uploads.getByRole('link', { name: 'Otvoriť' }).click();
    await expect(page.getByText('Súbor sa nepodarilo prečítať')).toBeVisible();
    await expect(page.getByText('Súbor sa nedá otvoriť.')).toBeVisible();

    // Read again, it fails the same way: wait for the second failure in the history, then
    // take the page as it then is (the form must not be replaced while it is being filled).
    await page.getByRole('button', { name: 'Prečítať znova' }).click();
    const [, , customerId, , invoiceId] = new URL(page.url()).pathname.split('/');
    await expect
      .poll(async () => {
        const answer = await page.request.get(
          `/api/customers/${customerId ?? ''}/invoices/${invoiceId ?? ''}/history`,
        );
        const history = (await answer.json()) as { items: { kind: string }[] };
        return history.items.filter((entry) => entry.kind === 'extraction_failed').length;
      }, READ)
      .toBe(2);
    await page.reload();
    await expect(page.getByText('Súbor sa nepodarilo prečítať')).toBeVisible();

    // Manual entry: the invoice keeps its file and gets its proposal.
    await page.getByLabel('Dátum zaúčtovania (rukou)', { exact: true }).fill('2026-06-23');
    await page.getByLabel('Poradové číslo dokladu (rukou)', { exact: true }).fill('144');
    await page.getByRole('textbox', { name: /^Názov/ }).fill('Slovak Telekom, a.s.');
    await page.getByLabel('IČO').fill('35763469');
    await page.getByRole('textbox', { name: /^Dátum vystavenia/ }).fill('2026-06-22');
    await page.getByRole('textbox', { name: /^Dátum dodania/ }).fill('2026-06-21');
    await page.getByRole('textbox', { name: /^Spolu na úhradu/ }).fill('93,71');
    await page.getByRole('button', { name: 'Uložiť a navrhnúť' }).click();
    await expect(
      page.getByRole('tab', { name: 'Návrh a zaúčtovanie', selected: true }),
    ).toBeVisible();
    await expect(page.getByRole('group', { name: 'Položka 632005 41 01 110 000' })).toBeVisible();
    await page.getByRole('tab', { name: 'História' }).click();
    await expect(page.getByRole('cell', { name: 'Zadaná ručne' })).toBeVisible();
  });

  await test.step('Úložisko lists the files with what they became, and passes axe', async () => {
    await openNav(page);
    await page.getByRole('navigation').getByRole('link', { name: 'Úložisko' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Úložisko' })).toBeVisible();
    const files = page.getByRole('table', { name: 'Súbory' });
    for (const file of [ZMOS, HORNBACH, ZSE, 'faktura-telekom.jpg']) {
      await expect(files.getByRole('link', { name: `Stiahnuť ${file}` })).toBeVisible();
    }
    await expect(files.getByRole('link', { name: 'Faktúra' })).toHaveCount(4);
    await checkA11y();
    expect(await scrollsHorizontally(page)).toBe(false);
    await page.emulateMedia({ colorScheme: 'dark' });
    await checkA11y();
  });
});
