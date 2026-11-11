import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { BOLDOG, LEHOTA, meAs } from '../test/me';
import { renderApp } from '../test/render';

function nav() {
  return screen.getByRole('navigation', { name: 'Hlavné menu' });
}

/** The menu's links (the Nová faktúra button, a link once a customer is chosen, is not one). */
function menuLinks() {
  return within(nav())
    .getAllByRole('link')
    .map((link) => link.getAttribute('aria-label') ?? link.textContent)
    .filter((name) => name !== 'Nová faktúra');
}

const CUSTOMER_ITEMS = ['Domov', 'Faktúry', 'Číselníky', 'Importy a exporty', 'Úložisko', 'Systém'];
const BOTTOM = ['Pomocník', 'Profil'];

describe('the navbar per role', () => {
  it('a customer user sees the customer items and Správy, and lands on its Domov', async () => {
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    const { router } = await renderApp('/');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/c/${BOLDOG.id}`);
    });
    expect(menuLinks()).toEqual([...CUSTOMER_ITEMS, 'Správy', ...BOTTOM]);
    expect(screen.queryByLabelText('Klient', { selector: 'input' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Domov' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Nová faktúra' })).toHaveAttribute(
      'href',
      `/c/${BOLDOG.id}/invoices/new`,
    );
    expect(within(nav()).getByRole('button', { name: 'Odhlásiť' })).toBeEnabled();
  });

  it('a viewer sees the same items', async () => {
    mockApi({ 'GET /api/me': { body: meAs('viewer') } });
    await renderApp(`/c/${BOLDOG.id}`);
    expect(menuLinks()).toEqual([...CUSTOMER_ITEMS, 'Správy', ...BOTTOM]);
    const button = screen.getByRole('button', { name: 'Nová faktúra' });
    expect(button).toBeDisabled();
    await userEvent.hover(button.parentElement ?? button);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'Faktúry tohto klienta môžete len prezerať.',
    );
  });

  it('staff land on Prehľad klientov and get the customer items once a customer is chosen', async () => {
    mockApi({ 'GET /api/me': { body: meAs('staff') } });
    const { router } = await renderApp('/');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/provider');
    });
    expect(menuLinks()).toEqual(['Správy', 'Prehľad klientov', 'Používatelia', ...BOTTOM]);
    await router.navigate({ to: '/c/$customerId', params: { customerId: BOLDOG.id } });
    await screen.findByRole('heading', { level: 1, name: 'Domov' });
    expect(menuLinks()).toEqual([
      ...CUSTOMER_ITEMS,
      'Správy',
      'Prehľad klientov',
      'Používatelia',
      ...BOTTOM,
    ]);
    expect(within(nav()).getByText('Servisný účet')).toBeInTheDocument();
  });

  it('an admin sees the provider and the admin items', async () => {
    mockApi({ 'GET /api/me': { body: meAs('admin') } });
    await renderApp('/users');
    expect(menuLinks()).toEqual([
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
    ]);
    expect(within(nav()).getByText('Administrácia')).toBeInTheDocument();
  });

  it('collapses to icons and remembers it', async () => {
    const user = userEvent.setup();
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    await renderApp(`/c/${BOLDOG.id}`);
    await user.click(screen.getByRole('button', { name: 'Zbaliť menu' }));
    expect(within(nav()).getByRole('link', { name: 'Faktúry' })).not.toHaveTextContent('Faktúry');
    expect(window.localStorage.getItem('riso-navbar-collapsed')).toBe('1');
    await user.click(screen.getByRole('button', { name: 'Rozbaliť menu' }));
    expect(within(nav()).getByRole('link', { name: 'Faktúry' })).toHaveTextContent('Faktúry');
  });
});

describe('the customer switcher', () => {
  it('opens another customer and keeps the screen', async () => {
    const user = userEvent.setup();
    mockApi({ 'GET /api/me': { body: meAs('staff') } });
    const { router } = await renderApp(`/c/${BOLDOG.id}/invoices`);
    const switcher = screen.getByLabelText('Klient', { selector: 'input' });
    expect(switcher).toHaveValue('Obec Boldog');
    await user.click(switcher);
    await user.click(await screen.findByRole('option', { name: LEHOTA.name }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/c/${LEHOTA.id}/invoices`);
    });
  });

  it('searches the customers', async () => {
    const user = userEvent.setup();
    mockApi({ 'GET /api/me': { body: meAs('admin') } });
    await renderApp('/users');
    const switcher = screen.getByLabelText('Klient', { selector: 'input' });
    expect(switcher).toHaveValue('');
    await user.type(switcher, 'Lehota');
    expect(await screen.findAllByRole('option')).toHaveLength(1);
  });
});

describe('guards', () => {
  it('sends an anonymous caller to the login with the way back', async () => {
    mockApi({ 'GET /api/me': { status: 401, body: { detail: 'not logged in' } } });
    const { router } = await renderApp(`/c/${BOLDOG.id}/invoices`);
    await screen.findByRole('heading', { level: 1, name: 'Prihlásenie' });
    expect(router.state.location.search).toEqual({ next: `/c/${BOLDOG.id}/invoices` });
  });

  it('a customer the caller cannot open is not found', async () => {
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    await renderApp('/c/someone-else');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Stránka sa nenašla' }),
    ).toBeInTheDocument();
    expect(nav()).toBeInTheDocument(); // inside the shell
  });

  it('an admin screen is forbidden to staff', async () => {
    mockApi({ 'GET /api/me': { body: meAs('staff') } });
    await renderApp('/admin/outbox');
    expect(
      screen.getByRole('heading', { level: 1, name: 'Prístup zamietnutý' }),
    ).toBeInTheDocument();
  });

  it('a later screen opens a Pripravujeme page', async () => {
    mockApi({ 'GET /api/me': { body: meAs('admin') } });
    await renderApp('/admin/jobs');
    expect(screen.getByRole('heading', { level: 1, name: 'Úlohy' })).toBeInTheDocument();
    expect(screen.getByText('Pripravujeme')).toBeInTheDocument();
  });

  it('Správy is a placeholder for everyone', async () => {
    mockApi({ 'GET /api/me': { body: meAs('viewer') } });
    await renderApp('/messages');
    expect(screen.getByText(/správy a upozornenia/)).toBeInTheDocument();
  });
});

describe('impersonation', () => {
  it('shows the amber banner and ends it', async () => {
    const user = userEvent.setup();
    const impersonating = meAs('user', {
      impersonation: {
        real_user_id: 'u-admin',
        real_user_name: 'Alena Správcová',
        reason: 'Hlásenie 42',
        started_at: '2026-06-11T08:00:00Z',
        expires_at: '2026-06-11T09:00:00Z',
      },
    });
    let ended = false;
    const { calls } = mockApi({
      'GET /api/me': () => ({ body: ended ? meAs('admin') : impersonating }),
      'POST /api/me/impersonation/end': () => {
        ended = true;
        return { status: 204 };
      },
    });
    const { router } = await renderApp(`/c/${BOLDOG.id}`);
    expect(screen.getByText('Ste prihlásený ako Jana Vzorová.')).toBeInTheDocument();
    expect(screen.getByText('Dôvod: Hlásenie 42')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Ukončiť' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/users');
    });
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/me/impersonation/end')).toBe(
      true,
    );
    expect(screen.queryByText(/Ste prihlásený ako/)).not.toBeInTheDocument();
  });
});

describe('logging out', () => {
  it('ends the session and shows the login', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('user') },
      'POST /api/auth/logout': { status: 204 },
    });
    const { router } = await renderApp(`/c/${BOLDOG.id}`);
    await user.click(within(nav()).getByRole('button', { name: 'Odhlásiť' }));
    await screen.findByText('Odhlásenie prebehlo.');
    expect(router.state.location.pathname).toBe('/login');
    expect(calls.map((c) => `${c.method} ${c.path}`)).toContain('POST /api/auth/logout');
  });
});

describe('the theme', () => {
  it('switches between the light and the dark theme', async () => {
    const user = userEvent.setup();
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    await renderApp(`/c/${BOLDOG.id}`);
    await user.click(screen.getByRole('button', { name: 'Prepnúť na tmavý režim' }));
    expect(document.documentElement).toHaveAttribute('data-mantine-color-scheme', 'dark');
    expect(window.localStorage.getItem('mantine-color-scheme-value')).toBe('dark');
    await user.click(screen.getByRole('button', { name: 'Prepnúť na svetlý režim' }));
    expect(document.documentElement).toHaveAttribute('data-mantine-color-scheme', 'light');
  });
});
