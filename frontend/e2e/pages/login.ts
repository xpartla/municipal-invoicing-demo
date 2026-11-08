import { expect, type Page } from '@playwright/test';

import { SEED_PASSWORD, USERS } from '../seed';

export type SeededRole = keyof typeof USERS;

/** Logs in through the login page and waits for the shell. */
export async function loginAs(page: Page, role: SeededRole, password = SEED_PASSWORD) {
  await page.goto('/login');
  await page.getByLabel('E-mail').fill(USERS[role].email);
  await page.getByLabel('Heslo', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Prihlásiť sa' }).click();
  await expect(page.getByRole('navigation', { name: 'Hlavné menu' })).toBeVisible();
}

/** Opens the navbar on narrow screens, where it is a drawer. */
export async function openNav(page: Page) {
  const burger = page.getByRole('button', { name: 'Zobraziť alebo skryť menu' });
  if (await burger.isVisible()) await burger.click();
}
