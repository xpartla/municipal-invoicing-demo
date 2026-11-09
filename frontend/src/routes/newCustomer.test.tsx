import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Nový klient (P2-M3-T09): staff copy Boldog with the options and invite the first login,
// then follow the copy job; an admin creates a new customer without a provider; a taken IČO
// sends the person back to the identity; a customer user cannot open the wizard.

const customer = {
  ...BOLDOG,
  dic: null,
  address: null,
  iban: null,
  variable_number: null,
  status: 'active',
  created_at: '2026-11-09T10:00:00Z',
  deleted_at: null,
};
const copyOut = { ...customer, id: 'c-copy', name: 'Obec Kópia', ico: '99900033' };
const directory = [{ customer, logins: [] }];

async function fill(user: ReturnType<typeof userEvent.setup>, label: string, value: string) {
  await user.type(screen.getByRole('textbox', { name: new RegExp(`^${label}`) }), value);
}

describe('Nový klient', () => {
  it('lets staff copy Boldog, invite the first login and follow the job', async () => {
    let polls = 0;
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('staff') },
      'GET /api/providers/p1/customers': { body: directory },
      'POST /api/providers/p1/customers/copy': {
        status: 202,
        body: { customer: copyOut, job_id: 'j1' },
      },
      'PUT /api/customers/c-copy/variable-number': { body: { ...copyOut, variable_number: '7' } },
      'POST /api/customers/c-copy/logins': { status: 201, body: { new_account: true } },
      'GET /api/customers/c-copy/jobs/j1': () => {
        polls += 1;
        return {
          body: {
            id: 'j1',
            kind: 'customer_copy',
            status: polls > 1 ? 'succeeded' : 'running',
            attempts: 1,
            max_attempts: 5,
            created_at: '2026-11-09T10:00:00Z',
            started_at: null,
            finished_at: null,
            last_error: null,
            result: { year: 2026, code_lists: ['accounts', 'budget_expense'], templates: 1 },
          },
        };
      },
    });
    const user = userEvent.setup();
    await renderApp('/users');
    await user.click(await screen.findByRole('link', { name: 'Nový klient' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Nový klient' }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: /Kópia jedného z vašich klientov/ }));
    const source = screen.getAllByLabelText('Kopírovať z klienta')[0];
    if (!source) throw new Error('no source select');
    await user.click(source);
    await user.click(await screen.findByRole('option', { name: 'Obec Boldog (00305863)' }));
    await user.click(screen.getByRole('button', { name: 'Ďalej' }));

    // The identity: a required name and IČO; the rest is optional.
    await user.click(await screen.findByRole('button', { name: 'Ďalej' }));
    expect(await screen.findAllByText('Toto pole je povinné.')).not.toHaveLength(0);
    await fill(user, 'Názov', 'Obec Kópia');
    await fill(user, 'IČO', '99900033');
    await fill(user, 'Variabilné číslo', '7');
    await user.click(screen.getByRole('button', { name: 'Ďalej' }));

    // What to copy: everything but the supplier memory, by default.
    const memory = await screen.findByRole('checkbox', { name: 'Pamäť dodávateľov' });
    expect(memory).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Číselníky (aktívne verzie)' })).toBeChecked();
    await user.click(memory);
    await user.click(screen.getByRole('button', { name: 'Ďalej' }));

    await user.click(await screen.findByRole('checkbox', { name: 'Pozvať prvé prihlásenie' }));
    await user.type(screen.getByRole('textbox', { name: 'E-mail' }), 'starosta@kopia.test');
    await user.type(screen.getByRole('textbox', { name: 'Meno a priezvisko' }), 'Starosta Kópie');
    await user.click(screen.getByRole('button', { name: 'Vytvoriť kópiu' }));

    expect(await screen.findByText('Klient Obec Kópia je vytvorený')).toBeInTheDocument();
    const copy = calls.find((c) => c.path === '/api/providers/p1/customers/copy');
    expect(copy?.body).toMatchObject({
      name: 'Obec Kópia',
      ico: '99900033',
      source_customer_id: BOLDOG.id,
      options: {
        year: new Date().getFullYear(),
        parameters: true,
        code_lists: true,
        conventions: true,
        templates: true,
        supplier_memory: true,
      },
    });
    expect(calls.find((c) => c.path.endsWith('/variable-number'))?.body).toEqual({
      variable_number: '7',
    });
    expect(calls.find((c) => c.path === '/api/customers/c-copy/logins')?.body).toEqual({
      email: 'starosta@kopia.test',
      name: 'Starosta Kópie',
      role: 'customer_user',
    });
    expect(
      await screen.findByText(
        'Hotovo: skopírovaných číselníkov 2, šablón 1.',
        {},
        { timeout: 3000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Otvoriť klienta' })).toHaveAttribute(
      'href',
      '/c/c-copy',
    );
  });

  it('lets an admin create a new customer without a provider', async () => {
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/customers': { body: directory },
      'GET /api/admin/providers': {
        body: [
          {
            provider: {
              id: 'p1',
              name: 'Účtovníctvo Vzor, s.r.o.',
              ico: null,
              status: 'active',
              created_at: '2026-01-01T07:00:00Z',
              removed_at: null,
            },
            staff: [],
            customers: [],
          },
        ],
      },
      'POST /api/admin/customers': { status: 201, body: copyOut },
    });
    const user = userEvent.setup();
    await renderApp('/users/new');
    await user.click(await screen.findByRole('button', { name: 'Ďalej' }));
    const [provider] = await screen.findAllByLabelText('Servisný účet');
    expect(provider).toHaveValue('Bez servisného účtu');
    await fill(user, 'Názov', 'Obec Kópia');
    await fill(user, 'IČO', '99900033');
    await user.click(screen.getByRole('button', { name: 'Ďalej' }));
    await user.click(await screen.findByRole('button', { name: 'Vytvoriť klienta' }));
    expect(await screen.findByText('Klient Obec Kópia je vytvorený')).toBeInTheDocument();
    expect(
      calls.find((c) => c.path === '/api/admin/customers' && c.method === 'POST')?.body,
    ).toEqual({
      name: 'Obec Kópia',
      ico: '99900033',
      dic: null,
      address: null,
      iban: null,
      provider_id: null,
    });
    expect(screen.queryByText('Kopírovanie')).not.toBeInTheDocument();
  });

  it('sends a taken IČO back to the identity', async () => {
    mockApi({
      'GET /api/me': { body: meAs('staff') },
      'GET /api/providers/p1/customers': { body: directory },
      'POST /api/providers/p1/customers': {
        status: 409,
        body: { detail: 'IČO taken', code: 'conflict' },
      },
    });
    const user = userEvent.setup();
    await renderApp('/users/new');
    await user.click(await screen.findByRole('button', { name: 'Ďalej' }));
    await fill(user, 'Názov', 'Obec Kópia');
    await fill(user, 'IČO', '00305863');
    await user.click(screen.getByRole('button', { name: 'Ďalej' }));
    await user.click(await screen.findByRole('button', { name: 'Vytvoriť klienta' }));
    expect(await screen.findByText('Toto IČO už má iný aktívny klient.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /^IČO/ })).toHaveValue('00305863');
  });

  it('is not for a customer’s user', async () => {
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    await renderApp('/users/new');
    const main = await screen.findByRole('main');
    expect(await within(main).findByText('Na túto stránku nemáte oprávnenie.')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Nový klient' })).not.toBeInTheDocument();
    });
  });
});
