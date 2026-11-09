import { expect, type Page } from '@playwright/test';

import { CUSTOMERS } from '../seed';
import { openNav } from './login';

/**
 * As staff: Používatelia → Nový klient → a copy of Boldog (its parameters, lists and
 * conventions; its supplier memory when asked), then opens the copy. The widths run in
 * parallel on one seeded database, so a spec that changes what others read works in a copy
 * of its own, under an IČO of its own.
 */
export async function copyBoldog(page: Page, name: string, ico: string, { memory = false } = {}) {
  await openNav(page);
  await page.getByRole('navigation').getByRole('link', { name: 'Používatelia' }).click();
  await page.getByRole('link', { name: 'Nový klient' }).click();
  await page.getByRole('radio', { name: /Kópia jedného z vašich klientov/ }).check();
  await page.getByRole('combobox', { name: 'Kopírovať z klienta' }).click();
  await page.getByRole('option', { name: new RegExp(CUSTOMERS.boldog) }).click();
  await page.getByRole('button', { name: 'Ďalej' }).click();
  await page.getByRole('textbox', { name: /^Názov/ }).fill(name);
  await page.getByRole('textbox', { name: /^IČO/ }).fill(ico);
  await page.getByRole('button', { name: 'Ďalej' }).click();
  if (memory) await page.getByRole('checkbox', { name: 'Pamäť dodávateľov' }).check();
  await page.getByRole('button', { name: 'Ďalej' }).click();
  await page.getByRole('button', { name: 'Vytvoriť kópiu' }).click();
  await expect(page.getByText(/^Hotovo: skopírovaných číselníkov [1-9]/)).toBeVisible({
    timeout: 15_000,
  });
  await page.getByRole('link', { name: 'Otvoriť klienta' }).click();
  await expect(page.getByText(`Prehľad klienta ${name}`)).toBeVisible();
}
