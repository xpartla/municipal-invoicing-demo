import { join } from 'node:path';

import { expect, scrollsHorizontally, test } from './fixtures';
import { copyBoldog } from './pages/customers';
import { loginAs, openNav } from './pages/login';

// Kontrola údajov (P2-M5-T10): an uploaded scan read through RecordedReader, its check step
// with the document viewer passes axe in both themes and fits each width (820 px: the
// viewer above the form). Úložisko (T11) then lists the scan with the invoice it became. Each width works in a copy of Boldog of its own, as the same file
// cannot be uploaded twice to one customer.

const COPY_ICO: Record<string, readonly string[]> = {
  phone: ['99900203', '99900238'],
  tablet: ['99900211', '99900246'],
  desktop: ['99900220', '99900254'],
};

const SAMPLES = join(import.meta.dirname, '..', '..', 'testdata', 'ocr', 'samples');

test('the check step of an uploaded scan and Úložisko pass axe and fit the width', async ({
  page,
  checkA11y,
}, testInfo) => {
  test.setTimeout(90_000);
  const ico = COPY_ICO[testInfo.project.name]?.[testInfo.retry];
  if (!ico) throw new Error(`no IČO for the width ${testInfo.project.name}`);
  await loginAs(page, 'staff');
  const name = `Obec Kontrola ${testInfo.project.name} ${String(testInfo.retry + 1)}`;
  await copyBoldog(page, name, ico);

  await openNav(page);
  await page.getByRole('link', { name: 'Nová faktúra' }).click();
  await page
    .getByLabel('Vybrať súbory')
    .setInputFiles(join(SAMPLES, 'heldout-19-telekom-phone.scan.jpg'));
  const table = page.getByRole('table', { name: 'Nahrané súbory' });
  await expect(table.getByText('Na kontrolu')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: 'Pokračovať na kontrolu (1)' }).click();

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

  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Úložisko' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Úložisko' })).toBeVisible();
  const files = page.getByRole('table', { name: 'Súbory' });
  await expect(
    files.getByRole('link', { name: 'Stiahnuť heldout-19-telekom-phone.scan.jpg' }),
  ).toBeVisible();
  await expect(files.getByRole('link', { name: 'Faktúra' })).toBeVisible();
  await checkA11y();
  expect(await scrollsHorizontally(page)).toBe(false);
  await page.emulateMedia({ colorScheme: 'dark' });
  await checkA11y();
});
