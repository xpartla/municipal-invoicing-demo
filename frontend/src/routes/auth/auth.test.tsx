import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../../test/api';
import { BOLDOG, meAs } from '../../test/me';
import { renderApp } from '../../test/render';

const ANONYMOUS = { status: 401, body: { detail: 'not logged in', code: 'unauthenticated' } };
const PASSWORD = 'Správne-heslo-2026';

describe('the login page', () => {
  it('logs in and lands where the role lands', async () => {
    const user = userEvent.setup();
    let me: unknown = null;
    const { calls } = mockApi({
      'GET /api/me': () => (me ? { body: me } : ANONYMOUS),
      'POST /api/auth/login': () => {
        me = meAs('user');
        return { body: me };
      },
    });
    const { router } = await renderApp('/login');
    await user.type(screen.getByLabelText('E-mail'), 'jana.vzorova@boldog.test');
    await user.type(screen.getByLabelText('Heslo'), PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Prihlásiť sa' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/c/${BOLDOG.id}`);
    });
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      email: 'jana.vzorova@boldog.test',
      password: PASSWORD,
    });
  });

  it('follows the way back after the login, within the app only', async () => {
    const user = userEvent.setup();
    mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/login': { body: meAs('staff') },
    });
    const { router } = await renderApp(`/login?next=${encodeURIComponent('/admin')}`);
    await user.type(screen.getByLabelText('E-mail'), 'peter@vzor.test');
    await user.type(screen.getByLabelText('Heslo'), PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Prihlásiť sa' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/admin');
    });
  });

  it('says nothing more than that the login failed', async () => {
    const user = userEvent.setup();
    mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/login': {
        status: 401,
        body: { detail: 'login failed', code: 'unauthenticated' },
      },
    });
    await renderApp('/login');
    await user.type(screen.getByLabelText('E-mail'), 'x@obec.sk');
    await user.type(screen.getByLabelText('Heslo'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Prihlásiť sa' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Nesprávny e-mail alebo heslo.');
  });

  it('tells how long to wait when throttled', async () => {
    const user = userEvent.setup();
    mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/login': {
        status: 429,
        body: { detail: 'too many', code: 'throttled', retry_after: 121 },
        headers: { 'Retry-After': '121' },
      },
    });
    await renderApp('/login');
    await user.type(screen.getByLabelText('E-mail'), 'x@obec.sk');
    await user.type(screen.getByLabelText('Heslo'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Prihlásiť sa' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Skúste to znova o 3 min.');
  });

  it('needs both fields', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({ 'GET /api/me': ANONYMOUS });
    await renderApp('/login');
    await user.click(screen.getByRole('button', { name: 'Prihlásiť sa' }));
    expect(await screen.findAllByText('Toto pole je povinné.')).toHaveLength(2);
    expect(calls.filter((c) => c.method === 'POST')).toEqual([]);
  });

  it('a logged-in caller is sent on: an admin to Platforma', async () => {
    mockApi({ 'GET /api/me': { body: meAs('admin') } });
    const { router } = await renderApp('/login');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/admin');
    });
  });
});

describe('the invitation page', () => {
  const info = {
    kind: 'invitation',
    name: 'Jana Vzorová',
    email: 'jana@obec.sk',
    expires_at: '2026-06-18T08:00:00Z',
  };

  it('greets the invited user and sets the password', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/token-info': { body: info },
      'POST /api/auth/invitation/accept': { status: 204 },
    });
    const { router } = await renderApp('/invitation#tok123');
    expect(await screen.findByText('Vitajte, Jana Vzorová.')).toBeInTheDocument();
    expect(screen.getByText('Nastavte si heslo k účtu jana@obec.sk.')).toBeInTheDocument();
    expect(screen.getByText('Odkaz platí do 18. 6. 2026 10:00.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Nové heslo'), PASSWORD);
    await user.type(screen.getByLabelText('Heslo znova'), PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Nastaviť heslo' }));
    await screen.findByText('Heslo je nastavené. Teraz sa prihláste.');
    expect(router.state.location.pathname).toBe('/login');
    expect(calls.find((c) => c.path === '/api/auth/invitation/accept')?.body).toEqual({
      token: 'tok123',
      password: PASSWORD,
    });
  });

  it('checks the length and the match before sending', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/token-info': { body: info },
    });
    await renderApp('/invitation#tok123');
    await user.type(await screen.findByLabelText('Nové heslo'), 'krátke');
    await user.type(screen.getByLabelText('Heslo znova'), 'iné');
    await user.click(screen.getByRole('button', { name: 'Nastaviť heslo' }));
    expect(await screen.findByText('Heslo musí mať aspoň 12 znakov.')).toBeInTheDocument();
    expect(calls.some((c) => c.path === '/api/auth/invitation/accept')).toBe(false);
  });

  it("shows the API's password policy on the field", async () => {
    const user = userEvent.setup();
    mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/token-info': { body: info },
      'POST /api/auth/invitation/accept': {
        status: 422,
        body: {
          detail: [{ loc: ['body', 'password'], msg: 'too common', type: 'password_common' }],
          code: 'validation_failed',
        },
      },
    });
    await renderApp('/invitation#tok123');
    await user.type(await screen.findByLabelText('Nové heslo'), 'password1234');
    await user.type(screen.getByLabelText('Heslo znova'), 'password1234');
    await user.click(screen.getByRole('button', { name: 'Nastaviť heslo' }));
    expect(
      await screen.findByText('Toto heslo je príliš bežné alebo jednoduché.'),
    ).toBeInTheDocument();
  });

  it('an invalid or missing link says so', async () => {
    mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/token-info': {
        status: 422,
        body: { detail: [{ loc: ['body', 'token'], msg: 'x', type: 'token_invalid' }] },
      },
    });
    await renderApp('/invitation#old');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Odkaz nie je platný' }),
    ).toBeInTheDocument();
  });
});

describe('the forgotten password page', () => {
  it('answers the same whatever the address', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/password-reset': { status: 202, body: { detail: 'sent' } },
    });
    await renderApp('/forgot-password');
    await user.type(screen.getByLabelText('E-mail'), 'nikto@obec.sk');
    await user.click(screen.getByRole('button', { name: 'Poslať odkaz' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Ak táto adresa patrí k účtu');
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ email: 'nikto@obec.sk' });
  });
});

describe('the reset page', () => {
  it('sets a new password from the link', async () => {
    const user = userEvent.setup();
    mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/token-info': {
        body: {
          kind: 'password_reset',
          name: 'Jana',
          email: 'jana@obec.sk',
          expires_at: '2026-06-11T09:00:00Z',
        },
      },
      'POST /api/auth/password-reset/complete': { status: 204 },
    });
    const { router } = await renderApp('/reset-password#r1');
    await user.type(await screen.findByLabelText('Nové heslo'), PASSWORD);
    await user.type(screen.getByLabelText('Heslo znova'), PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Uložiť nové heslo' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/login');
    });
  });

  it('refuses a token of another kind', async () => {
    mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/token-info': {
        body: {
          kind: 'invitation',
          name: 'Jana',
          email: 'j@o.sk',
          expires_at: '2026-06-18T08:00:00Z',
        },
      },
    });
    await renderApp('/reset-password#i1');
    expect(await screen.findByRole('heading', { name: 'Odkaz nie je platný' })).toBeInTheDocument();
  });
});

describe('the email confirmation page', () => {
  it('confirms with a button, not on opening', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/me': ANONYMOUS,
      'POST /api/auth/token-info': {
        body: {
          kind: 'email_change',
          name: 'Jana',
          email: 'nova@obec.sk',
          expires_at: '2026-06-12T08:00:00Z',
        },
      },
      'POST /api/auth/email-change/confirm': { status: 204 },
    });
    const { router } = await renderApp('/confirm-email#e1');
    expect(
      await screen.findByText('Vaša prihlasovacia adresa sa zmení na nova@obec.sk.'),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.path === '/api/auth/email-change/confirm')).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Potvrdiť zmenu' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/login');
    });
    expect(calls.some((c) => c.path === '/api/auth/email-change/confirm')).toBe(true);
  });
});
