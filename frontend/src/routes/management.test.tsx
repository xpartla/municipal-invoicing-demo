import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { BOLDOG, LEHOTA, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Profil, Používatelia, Servisné účty and Odoslané e-maily (P2-M1-T11): the forms, and the
// API's 422 problems landing on their fields.

const PASSWORD = 'Správne-heslo-2026';

function invalid(field: string[], type: string, msg = 'x') {
  return {
    status: 422,
    body: { detail: [{ loc: ['body', ...field], msg, type }], code: 'validation_failed' },
  };
}

const customer = {
  ...BOLDOG,
  dic: null,
  address: { street: 'Boldog 12', city: 'Boldog', postal_code: '92528', country: 'SK' },
  iban: null,
  variable_number: null,
  status: 'active',
  created_at: '2026-01-01T07:00:00Z',
  deleted_at: null,
};

const sessions = [
  {
    id: 's1',
    created_at: '2026-06-11T08:00:00Z',
    last_seen_at: '2026-06-11T08:00:00Z',
    expires_at: '2026-06-11T16:00:00Z',
    ip: '127.0.0.1',
    user_agent: null,
    current: true,
  },
  {
    id: 's2',
    created_at: '2026-06-10T08:00:00Z',
    last_seen_at: '2026-06-10T09:00:00Z',
    expires_at: '2026-06-10T17:00:00Z',
    ip: '10.0.0.2',
    user_agent: null,
    current: false,
  },
];

function profileApi(role: 'user' | 'staff', extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /api/me': { body: meAs(role) },
    'GET /api/me/sessions': { body: sessions },
    [`GET /api/customers/${BOLDOG.id}`]: { body: customer },
    ...extra,
  });
}

describe('Profil', () => {
  it('saves the personal fields', async () => {
    const user = userEvent.setup();
    const { calls } = profileApi('user', {
      'PATCH /api/me': ({ body }) => ({ body: { ...meAs('user').user, ...(body as object) } }),
    });
    await renderApp('/profile');
    const name = await screen.findByLabelText('Meno a priezvisko');
    await user.clear(name);
    await user.type(name, 'Jana Nová');
    await user.type(screen.getByLabelText(/E-mail na upozornenia/), 'posta@obec.sk');
    await user.click(
      within(screen.getByRole('region', { name: 'Osobné údaje' })).getByRole('button', {
        name: 'Uložiť',
      }),
    );
    await waitFor(() => {
      expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
        name: 'Jana Nová',
        notification_email: 'posta@obec.sk',
      });
    });
    expect(await screen.findByText('Osobné údaje sú uložené.')).toBeInTheDocument();
  });

  it("puts the API's 422 on the field", async () => {
    const user = userEvent.setup();
    profileApi('user', { 'PATCH /api/me': invalid(['notification_email'], 'email') });
    await renderApp('/profile');
    await user.type(await screen.findByLabelText(/E-mail na upozornenia/), 'nie');
    await user.click(
      within(screen.getByRole('region', { name: 'Osobné údaje' })).getByRole('button', {
        name: 'Uložiť',
      }),
    );
    expect(await screen.findByText('Toto nie je platná e-mailová adresa.')).toBeInTheDocument();
  });

  it('changes the password, with a wrong current one on its field', async () => {
    const user = userEvent.setup();
    let attempt = 0;
    const { calls } = profileApi('user', {
      'POST /api/me/password': () =>
        ++attempt === 1 ? invalid(['current_password'], 'password_wrong') : { status: 204 },
    });
    await renderApp('/profile');
    const section = await screen.findByRole('region', { name: 'Zmena hesla' });
    await user.type(within(section).getByLabelText('Súčasné heslo'), 'zlé');
    await user.type(within(section).getByLabelText(/^Nové heslo/), PASSWORD);
    await user.type(within(section).getByLabelText('Heslo znova'), PASSWORD);
    await user.click(within(section).getByRole('button', { name: 'Zmeniť heslo' }));
    expect(await screen.findByText('Heslo nie je správne.')).toBeInTheDocument();
    expect(calls.filter((c) => c.path === '/api/me/password')).toHaveLength(1);
  });

  it('lists the sessions and logs out everywhere after asking', async () => {
    const user = userEvent.setup();
    const { calls } = profileApi('user', { 'POST /api/auth/logout-all': { status: 204 } });
    const { router } = await renderApp('/profile');
    await screen.findByText('Toto zariadenie');
    const table = screen.getByRole('region', { name: 'Zoznam prihlásení' });
    expect(within(within(table).getByRole('table')).getAllByRole('row')).toHaveLength(3);
    await user.click(screen.getByRole('button', { name: 'Odhlásiť všade' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Odhlásiť všade' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/login');
    });
    expect(calls.some((c) => c.path === '/api/auth/logout-all')).toBe(true);
  });

  it('disables the credential sections while impersonating', async () => {
    mockApi({
      'GET /api/me': {
        body: meAs('user', {
          impersonation: {
            real_user_id: 'u-admin',
            real_user_name: 'Alena',
            reason: 'x',
            started_at: '2026-06-11T08:00:00Z',
            expires_at: '2026-06-11T09:00:00Z',
          },
        }),
      },
      'GET /api/me/sessions': { body: sessions },
      [`GET /api/customers/${BOLDOG.id}`]: { body: customer },
    });
    await renderApp('/profile');
    expect(await screen.findByRole('button', { name: 'Zmeniť heslo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Poslať potvrdenie' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Odhlásiť všade' })).toBeDisabled();
    expect(screen.getByLabelText('Meno a priezvisko')).toBeEnabled();
  });

  it('the customer user edits the address but not the name or the IČO', async () => {
    const user = userEvent.setup();
    const { calls } = profileApi('user', {
      [`PATCH /api/customers/${BOLDOG.id}/contact`]: invalid(
        ['address', 'postal_code'],
        'postal_code',
      ),
    });
    await renderApp('/profile');
    expect(await screen.findByLabelText('Názov')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('IČO')).toHaveAttribute('readonly');
    expect(
      screen.getByText('Názov, IČO a DIČ mení servisný účet alebo administrátor.'),
    ).toBeInTheDocument();
    const code = screen.getByLabelText('PSČ');
    await user.clear(code);
    await user.type(code, '9');
    await user.click(screen.getByRole('button', { name: 'Uložiť adresu a účet' }));
    expect(await screen.findByText('PSČ nie je platné.')).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      address: { street: 'Boldog 12', city: 'Boldog', postal_code: '9', country: 'SK' },
      iban: null,
    });
  });

  it('staff edit the identity; a taken IČO lands on its field', async () => {
    const user = userEvent.setup();
    profileApi('staff', {
      [`PATCH /api/customers/${BOLDOG.id}/identity`]: {
        status: 409,
        body: { detail: 'IČO is used', code: 'conflict' },
      },
    });
    await renderApp(`/profile`);
    const ico = await screen.findByLabelText('IČO');
    expect(ico).not.toHaveAttribute('readonly');
    await user.clear(ico);
    await user.type(ico, '99900017');
    await user.click(screen.getByRole('button', { name: 'Uložiť názov, IČO a DIČ' }));
    expect(await screen.findByText('Toto IČO už má iný aktívny klient.')).toBeInTheDocument();
  });
});

// Používatelia ------------------------------------------------------------------------------

const directory = [
  {
    customer,
    logins: [
      {
        user_id: 'u-user',
        name: 'Jana Vzorová',
        email: 'jana.vzorova@boldog.test',
        role: 'customer_user',
        active: true,
        status: 'active',
        locked: false,
      },
    ],
  },
  { customer: { ...customer, ...LEHOTA }, logins: [] },
];

describe('Používatelia for staff', () => {
  it('lists the customers with their logins', async () => {
    mockApi({
      'GET /api/me': { body: meAs('staff') },
      'GET /api/providers/p1/customers': { body: directory },
    });
    await renderApp('/users');
    const boldog = await screen.findByRole('region', { name: 'Obec Boldog' });
    expect(within(boldog).getByText('Jana Vzorová')).toBeInTheDocument();
    expect(within(boldog).getByText('Používateľ')).toBeInTheDocument();
    const lehota = screen.getByRole('region', { name: LEHOTA.name });
    expect(within(lehota).getByText('Klient zatiaľ nemá žiadne prihlásenie.')).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Všetky účty' })).not.toBeInTheDocument();
  });

  it('invites a login; an address with access already lands on the field', async () => {
    const user = userEvent.setup();
    let attempt = 0;
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('staff') },
      'GET /api/providers/p1/customers': { body: directory },
      [`POST /api/customers/${LEHOTA.id}/logins`]: () =>
        ++attempt === 1
          ? { status: 409, body: { detail: 'exists', code: 'conflict' } }
          : { status: 201, body: { user: meAs('viewer').user, new_account: true } },
    });
    await renderApp('/users');
    const lehota = await screen.findByRole('region', { name: LEHOTA.name });
    await user.click(within(lehota).getByRole('button', { name: 'Pozvať prihlásenie' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('E-mail'), 'ivan@lehota.test');
    await user.type(within(dialog).getByLabelText('Meno a priezvisko'), 'Ivan Čitateľ');
    await user.click(within(dialog).getByLabelText('Rola', { selector: 'input' }));
    await user.click(await screen.findByRole('option', { name: 'Iba na čítanie' }));
    await user.click(within(dialog).getByRole('button', { name: 'Poslať pozvánku' }));
    expect(await within(dialog).findByText(/už má prístup k tomuto klientovi/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Poslať pozvánku' }));
    expect(await screen.findByText('Pozvánka je odoslaná.')).toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'POST').pop()?.body).toEqual({
      email: 'ivan@lehota.test',
      name: 'Ivan Čitateľ',
      role: 'customer_viewer',
    });
  });

  it('deactivates a login after asking, and sends a reset link', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('staff') },
      'GET /api/providers/p1/customers': { body: directory },
      [`POST /api/customers/${BOLDOG.id}/logins/u-user/deactivate`]: { body: meAs('user').user },
      [`POST /api/customers/${BOLDOG.id}/logins/u-user/reset-link`]: {
        body: { kind: 'password_reset' },
      },
    });
    await renderApp('/users');
    await user.click(await screen.findByRole('button', { name: 'Akcie: Jana Vzorová' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Deaktivovať' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Účet zostane/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Deaktivovať' }));
    expect(await screen.findByText('Prihlásenie je deaktivované.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Akcie: Jana Vzorová' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Poslať odkaz na heslo' }));
    expect(await screen.findByText('Odkaz je odoslaný.')).toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual([
      `/api/customers/${BOLDOG.id}/logins/u-user/deactivate`,
      `/api/customers/${BOLDOG.id}/logins/u-user/reset-link`,
    ]);
  });

  it('assigns the variable number, with a bad one on the field', async () => {
    const user = userEvent.setup();
    mockApi({
      'GET /api/me': { body: meAs('staff') },
      'GET /api/providers/p1/customers': { body: directory },
      [`PUT /api/customers/${BOLDOG.id}/variable-number`]: invalid(
        ['variable_number'],
        'variable_number',
      ),
    });
    await renderApp('/users');
    const boldog = await screen.findByRole('region', { name: 'Obec Boldog' });
    await user.click(within(boldog).getByRole('button', { name: 'Prideliť VS' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/^Variabilný symbol/), '12a');
    await user.click(within(dialog).getByRole('button', { name: 'Uložiť' }));
    expect(
      await within(dialog).findByText('Variabilný symbol má jednu až desať číslic.'),
    ).toBeInTheDocument();
  });
});

describe('Používatelia for admins', () => {
  const accounts = {
    items: [
      { ...meAs('user').user, memberships: [] },
      {
        ...meAs('admin').user,
        memberships: [
          { id: 'm', scope_kind: 'platform', scope_id: null, role: 'platform_admin', active: true },
        ],
      },
    ],
    total: 2,
  };

  it('locks an account after asking', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/customers': { body: directory },
      'GET /api/admin/users': { body: accounts },
      'POST /api/admin/users/u-user/lock': { body: { ...meAs('user').user, locked: true } },
    });
    await renderApp('/users');
    await user.click(await screen.findByRole('tab', { name: 'Všetky účty' }));
    await user.click(await screen.findByRole('button', { name: 'Akcie: Jana Vzorová' }));
    expect(
      screen.queryByRole('button', { name: 'Akcie: Alena Správcová' }),
    ).not.toBeInTheDocument();
    await user.click(await screen.findByRole('menuitem', { name: 'Zablokovať' }));
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Zablokovať' }),
    );
    await waitFor(() => {
      expect(calls.some((c) => c.path === '/api/admin/users/u-user/lock')).toBe(true);
    });
  });

  it('impersonates with a required reason', async () => {
    const user = userEvent.setup();
    let impersonating = false;
    const { calls } = mockApi({
      'GET /api/me': () => ({
        body: impersonating
          ? meAs('user', {
              impersonation: {
                real_user_id: 'u-admin',
                real_user_name: 'Alena Správcová',
                reason: 'Hlásenie 42',
                started_at: '2026-06-11T08:00:00Z',
                expires_at: '2026-06-11T09:00:00Z',
              },
            })
          : meAs('admin'),
      }),
      'GET /api/admin/customers': { body: directory },
      'POST /api/admin/users/u-user/impersonate': () => {
        impersonating = true;
        return { status: 204 };
      },
    });
    const { router } = await renderApp('/users');
    await user.click(await screen.findByRole('button', { name: 'Akcie: Jana Vzorová' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Prihlásiť sa ako' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Prihlásiť sa ako Jana Vzorová' }));
    expect(await within(dialog).findByText('Toto pole je povinné.')).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/^Dôvod/), 'Hlásenie 42');
    await user.click(within(dialog).getByRole('button', { name: 'Prihlásiť sa ako Jana Vzorová' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/c/${BOLDOG.id}`);
    });
    expect(screen.getByText('Ste prihlásený ako Jana Vzorová.')).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ reason: 'Hlásenie 42' });
  });
});

// Servisné účty and Odoslané e-maily ---------------------------------------------------------

describe('Servisné účty', () => {
  const providers = [
    {
      provider: {
        id: 'p1',
        name: 'Účtovníctvo Vzor, s.r.o.',
        ico: null,
        status: 'active',
        created_at: '2026-01-01T07:00:00Z',
        removed_at: null,
      },
      staff: [
        {
          user_id: 'u-staff',
          name: 'Peter Účtovník',
          email: 'peter@vzor.test',
          role: 'provider_staff',
          active: true,
          status: 'active',
          locked: false,
        },
      ],
      customers: [customer],
    },
  ];
  const all = [
    ...directory,
    {
      customer: { ...customer, id: 'c-alone', name: 'Obec Nezávislá', provider_id: null },
      logins: [],
    },
  ];

  it('creates a provider, with a bad IČO on its field', async () => {
    const user = userEvent.setup();
    mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/providers': { body: providers },
      'GET /api/admin/customers': { body: all },
      'POST /api/admin/providers': invalid(['ico'], 'ico_check_digit'),
    });
    await renderApp('/admin/providers');
    await user.click(await screen.findByRole('button', { name: 'Nový servisný účet' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Názov'), 'Agát');
    await user.type(within(dialog).getByLabelText('IČO (nepovinné)'), '123');
    await user.click(within(dialog).getByRole('button', { name: 'Vytvoriť' }));
    expect(
      await within(dialog).findByText('IČO nemá správnu kontrolnú číslicu.'),
    ).toBeInTheDocument();
  });

  it('assigns an unassigned customer and adds staff', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/providers': { body: providers },
      'GET /api/admin/customers': { body: all },
      'PUT /api/admin/customers/c-alone/provider': { body: customer },
      'POST /api/admin/providers/p1/staff': {
        status: 201,
        body: { user: meAs('staff').user, new_account: true },
      },
    });
    await renderApp('/admin/providers');
    const card = await screen.findByRole('region', { name: 'Účtovníctvo Vzor, s.r.o.' });
    expect(within(card).getByText('Peter Účtovník')).toBeInTheDocument();
    await user.click(within(card).getByLabelText('Priradiť klienta', { selector: 'input' }));
    await user.click(await screen.findByRole('option', { name: 'Obec Nezávislá' }));
    await user.click(within(card).getByRole('button', { name: 'Priradiť' }));
    await user.click(within(card).getByRole('button', { name: 'Pridať pracovníka' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('E-mail'), 'eva@vzor.test');
    await user.type(within(dialog).getByLabelText('Meno a priezvisko'), 'Eva Nová');
    await user.click(within(dialog).getByRole('button', { name: 'Pozvať' }));
    await waitFor(() => {
      expect(
        calls.filter((c) => c.method !== 'GET').map((c) => [c.method, c.path, c.body]),
      ).toEqual([
        ['PUT', '/api/admin/customers/c-alone/provider', { provider_id: 'p1' }],
        ['POST', '/api/admin/providers/p1/staff', { email: 'eva@vzor.test', name: 'Eva Nová' }],
      ]);
    });
  });
});

describe('Odoslané e-maily', () => {
  it('lists the outbox and shows a message with its link', async () => {
    const user = userEvent.setup();
    mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/outbox': {
        body: {
          items: [
            {
              id: 'm1',
              created_at: '2026-06-11T08:00:00Z',
              to_address: 'ivan@lehota.test',
              subject: 'Pozvánka do riso: Obec Boldog',
              template: 'invitation',
              customer_id: BOLDOG.id,
              user_id: 'u-x',
              sent_at: null,
            },
          ],
          total: 1,
        },
      },
      'GET /api/admin/outbox/m1': {
        body: {
          id: 'm1',
          created_at: '2026-06-11T08:00:00Z',
          to_address: 'ivan@lehota.test',
          subject: 'Pozvánka do riso: Obec Boldog',
          template: 'invitation',
          customer_id: BOLDOG.id,
          user_id: 'u-x',
          sent_at: null,
          body: 'Dobrý deň,\n\nodkaz:\nhttp://localhost:8001/invitation#abc\n\nriso\n',
        },
      },
    });
    await renderApp('/admin/outbox');
    await user.click(await screen.findByRole('button', { name: 'Pozvánka do riso: Obec Boldog' }));
    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByRole('link', { name: 'http://localhost:8001/invitation#abc' }),
    ).toHaveAttribute('href', 'http://localhost:8001/invitation#abc');
  });
});
