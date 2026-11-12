import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../lib/apiError';
import { errorMessage } from '../lib/errorMessage';
import i18n from '../i18n';
import { mockApi } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// The states every screen shares (P2-M8-T02): a load that failed says what went wrong and
// tries again; a session that ended sends the caller to the login and back; a crash of a
// screen shows inside the shell.

const base = `/api/customers/${BOLDOG.id}`;
const NONE = { count: 0, size: 0 };
const LISTING = {
  items: [],
  total: 0,
  size: 0,
  kinds: { document: NONE, import: NONE, export: NONE },
};

describe('errorMessage', () => {
  const t = i18n.t.bind(i18n);
  it('names the API error code, a server failure, an unreachable server', () => {
    expect(errorMessage(new ApiError(409, { code: 'conflict' }), t)).toBe(
      i18n.t('errors.conflict'),
    );
    expect(errorMessage(new ApiError(500, null), t)).toMatch(/Na serveri nastala chyba/);
    expect(errorMessage(new ApiError(400, { code: 'no_such_code' }), t)).toBe(
      i18n.t('common.error'),
    );
    expect(errorMessage(new TypeError('Failed to fetch'), t)).toMatch(/Server je nedostupný/);
    expect(errorMessage(new Error('?'), t)).toBe(i18n.t('common.error'));
  });
});

describe('a load that failed', () => {
  it('says so, not that the list is empty, and tries again', async () => {
    let failing = true;
    mockApi({
      'GET /api/me': { body: meAs('user') },
      [`GET ${base}/files`]: () =>
        failing ? { status: 500, body: { detail: 'boom' } } : { body: LISTING },
    });
    await renderApp(`/c/${BOLDOG.id}/files`);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Údaje sa nepodarilo načítať');
    expect(alert).toHaveTextContent('Na serveri nastala chyba');
    expect(screen.queryByText('Klient zatiaľ nemá žiadne súbory.')).not.toBeInTheDocument();

    failing = false;
    await userEvent.click(within(alert).getByRole('button', { name: 'Skúsiť znova' }));
    expect(await screen.findByText('Klient zatiaľ nemá žiadne súbory.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('a session that ended', () => {
  it('sends the caller to the login with a notice, and the login back to the page', async () => {
    let loggedIn = true;
    mockApi({
      'GET /api/me': () => (loggedIn ? { body: meAs('user') } : { status: 401, body: {} }),
      [`GET ${base}/files`]: () =>
        loggedIn ? { body: LISTING } : { status: 401, body: { code: 'unauthenticated' } },
      'POST /api/auth/login': () => {
        loggedIn = true;
        return { body: meAs('user') };
      },
    });
    const { router, queryClient } = await renderApp(`/c/${BOLDOG.id}/files`);
    await screen.findByText('Klient zatiaľ nemá žiadne súbory.');

    loggedIn = false;
    await queryClient.invalidateQueries({ queryKey: ['files'] });
    await router.invalidate();
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/login');
    });
    expect(router.state.location.search).toMatchObject({
      notice: 'session-expired',
      next: `/c/${BOLDOG.id}/files`,
    });
    expect(await screen.findByText('Prihlásenie vypršalo. Prihláste sa znova.')).toBeVisible();

    await userEvent.type(screen.getByLabelText('E-mail'), 'jana.vzorova@boldog.test');
    await userEvent.type(screen.getByLabelText('Heslo'), 'Ukážkové-heslo-2026');
    await userEvent.click(screen.getByRole('button', { name: 'Prihlásiť sa' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/c/${BOLDOG.id}/files`);
    });
  });

  it('does not show the notice after a logout', async () => {
    mockApi({
      'GET /api/me': { body: meAs('user') },
      'POST /api/auth/logout': { status: 204 },
    });
    const { router } = await renderApp('/messages');
    await userEvent.click(screen.getByRole('button', { name: 'Odhlásiť' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/login');
    });
    expect(await screen.findByText('Odhlásenie prebehlo.')).toBeVisible();
    expect(screen.queryByText(/Prihlásenie vypršalo/)).not.toBeInTheDocument();
  });
});

describe('a screen that crashed', () => {
  it('shows the error inside the shell, with a way to reload', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mockApi({
      'GET /api/me': { body: meAs('user') },
      // Not a dashboard: Domov fails on reading it.
      [`GET ${base}/dashboard`]: { body: { month: '2026-01' } },
    });
    await renderApp(`/c/${BOLDOG.id}`);
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Niečo sa pokazilo' }),
    ).toBeVisible();
    expect(screen.getByRole('navigation', { name: 'Hlavné menu' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Načítať znova' })).toBeEnabled();
    expect(screen.getAllByRole('main')).toHaveLength(1);
  });
});

describe('an address that does not exist', () => {
  it('says so inside the shell', async () => {
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    await renderApp('/nic-take');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Stránka sa nenašla' }),
    ).toBeVisible();
    expect(screen.getByRole('navigation', { name: 'Hlavné menu' })).toBeVisible();
  });
});
