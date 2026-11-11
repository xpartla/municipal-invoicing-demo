import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// The admin tools (P2-M7-T05, plan §10.9, decision 67): the audit viewer with its filters in
// the URL, Úlohy with retry, cancel and the customer data export, and Vyhodnotenie.

const customer = {
  ...BOLDOG,
  dic: null,
  address: null,
  iban: null,
  variable_number: null,
  status: 'active',
  created_at: '2026-01-01T07:00:00Z',
  deleted_at: null,
};
const DIRECTORY = [{ customer, logins: [] }];

function account(id: string, name: string, email: string) {
  return {
    id,
    name,
    email,
    notification_email: null,
    status: 'active',
    locked: false,
    memberships: [],
  };
}
const USERS = {
  items: [
    account('u-admin', 'Alena Správcová', 'admin@riso.test'),
    account('u-user', 'Jana Vzorová', 'jana.vzorova@boldog.test'),
  ],
  total: 2,
};

function event(id: string, action: string, extra: object = {}) {
  return {
    id,
    at: '2026-11-10T09:15:00Z',
    action,
    actor_id: 'u-user',
    real_actor_id: null,
    customer_id: BOLDOG.id,
    target_type: 'invoice',
    target_id: 'inv-1',
    details: { number: 'FD/144/26' },
    request_id: 'r1',
    ip: '127.0.0.1',
    ...extra,
  };
}

describe('Audit', () => {
  it('shows the log with names and keeps the filters in the URL', async () => {
    const api = mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/users': { body: USERS },
      'GET /api/admin/customers': { body: DIRECTORY },
      'GET /api/admin/audit': {
        body: {
          items: [
            event('e2', 'invoice.booked'),
            event('e1', 'impersonation.started', {
              actor_id: 'u-user',
              real_actor_id: 'u-admin',
              customer_id: null,
              details: {},
            }),
          ],
          total: 2,
        },
      },
    });
    const { router } = await renderApp('/admin/audit');
    const table = await screen.findByRole('region', { name: 'Záznamy auditu' });
    const booked = within(table).getByRole('row', { name: /invoice\.booked/ });
    expect(booked).toHaveTextContent('10. 11. 2026 10:15');
    expect(booked).toHaveTextContent('Jana Vzorová');
    expect(booked).toHaveTextContent('Obec Boldog');
    expect(booked).toHaveTextContent('{"number":"FD/144/26"}');
    expect(within(table).getByRole('row', { name: /impersonation/ })).toHaveTextContent(
      'v skutočnosti Alena Správcová',
    );
    expect(screen.getByText('2 záznamy')).toBeVisible();

    await userEvent.type(screen.getByRole('textbox', { name: 'Akcia' }), 'invoice.');
    await userEvent.type(screen.getByLabelText('Od'), '2026-11-01');
    await userEvent.click(screen.getByRole('button', { name: 'Hľadať' }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({
        action: 'invoice.',
        from: '2026-11-01',
      });
    });
    const last = api.calls.filter((c) => c.path.startsWith('/api/admin/audit')).at(-1);
    expect(last?.path).toContain('action=invoice.');
    // 1 November in Bratislava starts at 23:00 UTC the day before.
    expect(last?.path).toContain('since=2026-10-31T23%3A00%3A00Z');
  });

  it('says when nothing matches', async () => {
    mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/users': { body: USERS },
      'GET /api/admin/customers': { body: DIRECTORY },
      'GET /api/admin/audit': { body: { items: [], total: 0 } },
    });
    await renderApp('/admin/audit?action=nothing.');
    expect(await screen.findByText('Filtrom nezodpovedá žiadny záznam.')).toBeVisible();
    expect(screen.getByRole('textbox', { name: 'Akcia' })).toHaveValue('nothing.');
  });
});

function job(id: string, status: string, extra: object = {}) {
  return {
    id,
    kind: 'import_dry_run',
    status,
    attempts: 1,
    max_attempts: 3,
    created_at: '2026-11-10T09:00:00Z',
    started_at: null,
    finished_at: null,
    customer_id: BOLDOG.id,
    created_by: 'u-user',
    last_error: null,
    result: null,
    ...extra,
  };
}

describe('Úlohy', () => {
  it('lists the jobs, retries a failed one, cancels a queued one, downloads an export', async () => {
    const api = mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/users': { body: USERS },
      'GET /api/admin/customers': { body: DIRECTORY },
      'GET /api/admin/jobs': {
        body: {
          items: [
            job('j-failed', 'failed', { attempts: 3, last_error: 'the file is unreadable' }),
            job('j-queued', 'queued', { attempts: 0 }),
            job('j-export', 'succeeded', {
              kind: 'data_export',
              result: { size: 2048, name: 'riso-udaje-00305863-2026-11-10.zip' },
            }),
          ],
          total: 3,
          kinds: ['data_export', 'import_dry_run'],
        },
      },
      'POST /api/admin/jobs/j-failed/retry': { body: job('j-failed', 'queued') },
      'POST /api/admin/jobs/j-queued/cancel': { body: job('j-queued', 'cancelled') },
    });
    await renderApp('/admin/jobs');
    const table = await screen.findByRole('region', { name: 'Úlohy na pozadí' });
    const failed = within(table).getByRole('row', { name: /Neúspešná/ });
    expect(failed).toHaveTextContent('Skúška importu');
    expect(failed).toHaveTextContent('Obec Boldog');
    expect(failed).toHaveTextContent('Jana Vzorová');
    expect(failed).toHaveTextContent('3 z 3');
    expect(failed).toHaveTextContent('the file is unreadable');
    await userEvent.click(
      within(failed).getByRole('button', { name: 'Spustiť znova úlohu Skúška importu' }),
    );
    await waitFor(() => {
      expect(api.calls.some((c) => c.path === '/api/admin/jobs/j-failed/retry')).toBe(true);
    });
    const queued = within(table).getByRole('row', { name: /Čaká/ });
    await userEvent.click(
      within(queued).getByRole('button', { name: 'Zrušiť úlohu Skúška importu' }),
    );
    await waitFor(() => {
      expect(api.calls.some((c) => c.path === '/api/admin/jobs/j-queued/cancel')).toBe(true);
    });
    expect(
      within(table).getByRole('link', { name: 'Stiahnuť export údajov klienta Obec Boldog' }),
    ).toHaveAttribute('href', '/api/admin/jobs/j-export/file');
  });

  it('starts a customer data export', async () => {
    const api = mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/users': { body: USERS },
      'GET /api/admin/customers': { body: DIRECTORY },
      'GET /api/admin/jobs': { body: { items: [], total: 0, kinds: [] } },
      [`POST /api/admin/customers/${BOLDOG.id}/data-export`]: { body: { id: 'j-new' } },
    });
    await renderApp('/admin/jobs');
    expect(await screen.findByText('Filtrom nezodpovedá žiadna úloha.')).toBeVisible();
    const exporting = screen.getByRole('region', { name: 'Export údajov klienta' });
    expect(within(exporting).getByRole('button', { name: 'Exportovať údaje' })).toBeDisabled();
    await userEvent.click(within(exporting).getByRole('combobox', { name: 'Klient' }));
    await userEvent.click(screen.getByRole('option', { name: 'Obec Boldog' }));
    await userEvent.click(within(exporting).getByRole('button', { name: 'Exportovať údaje' }));
    await waitFor(() => {
      expect(
        api.calls.some(
          (c) => c.method === 'POST' && c.path === `/api/admin/customers/${BOLDOG.id}/data-export`,
        ),
      ).toBe(true);
    });
    expect(await screen.findByText(/Export sa pripravuje/)).toBeVisible();
  });
});

const REPORT = {
  entity_ico: '00305863',
  split: 'heldout',
  memory: 'frozen',
  generated_at: '2026-11-11T14:13:22Z',
  engine_version: '0.1.0',
  bundle_id: '00305863/2026-08',
  dataset_sha256: '78e2c243d28ce632b5f24103fde1c05fb284b6eacad7c3eaa10b5864ceb595e8',
  precedent_cases: 33,
  metrics: {
    correct: { hits: 19, n: 40, value: 0.475 },
    full_key: { hits: 24, n: 39, value: 0.6154 },
  },
  targets: [{ metric: 'full_key', target: 0.6, value: 0.6154, met: true }],
  by_supplier: {
    known: { correct: { hits: 9, n: 14, value: 0.643 } },
    new: { correct: { hits: 10, n: 26, value: 0.385 } },
  },
  by_tag: { energy: { correct: { hits: 3, n: 4, value: 0.75 } } },
  cases: [
    {
      case_id: 'heldout-05-zse-electricity-kd',
      tags: ['energy'],
      supplier: 'Západoslovenská energetika, a.s.',
      known_supplier: true,
      expected_outcome: 'coded',
      expected: [{ key: '632001 41 08 209 000', md: '502 000', dal: '321 000' }],
      proposed: [{ key: '632001 41 01 110 000', md: '502 000', dal: '321 000' }],
      alternatives: [],
      correct: false,
      full_key: false,
      fields: {},
      top3: true,
      split_ok: true,
      validation_ok: true,
      number_ok: true,
      date_ok: true,
      needs_review: false,
      review_reasons: [],
      confidence: 0.9,
    },
    {
      case_id: 'heldout-06-telekom-fees',
      tags: ['telecom'],
      supplier: 'Slovak Telekom, a.s.',
      known_supplier: true,
      expected_outcome: 'coded',
      expected: [{ key: '632005 41 01 110 000', md: '518 003', dal: '321 000' }],
      proposed: [{ key: '632005 41 01 110 000', md: '518 003', dal: '321 000' }],
      alternatives: [],
      correct: true,
      full_key: true,
      fields: {},
      top3: true,
      split_ok: true,
      validation_ok: true,
      number_ok: true,
      date_ok: true,
      needs_review: false,
      review_reasons: [],
      confidence: 0.95,
    },
  ],
};

describe('Vyhodnotenie', () => {
  it('shows the targets, the metrics, the groups and the wrong cases, and refreshes', async () => {
    const api = mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/eval': { body: REPORT },
    });
    await renderApp('/admin/eval');
    const targets = await screen.findByRole('list', { name: 'Ciele' });
    expect(within(targets).getByRole('listitem')).toHaveTextContent('Celá rozpočtová položka');
    expect(within(targets).getByRole('listitem')).toHaveTextContent(/61,5\s%/);
    expect(within(targets).getByRole('listitem')).toHaveTextContent('splnený');
    expect(screen.getByText(/2 faktúry, pamäť dodávateľov z 33 skenov/)).toBeVisible();
    const metrics = screen.getByRole('region', { name: 'Ukazovatele' });
    expect(
      within(metrics).getByRole('row', { name: /Celý výsledok správne\s*47,5\s%\s*19 z 40/ }),
    ).toBeVisible();
    const groups = screen.getByRole('region', { name: 'Podľa dodávateľa a druhu faktúry' });
    expect(
      within(groups).getByRole('row', { name: /Známy dodávateľ\s*14\s*64,3\s%/ }),
    ).toBeVisible();
    expect(within(groups).getByRole('row', { name: /energie/ })).toBeVisible();
    const cases = screen.getByRole('region', { name: 'Faktúry' });
    expect(within(cases).getAllByRole('row')).toHaveLength(2); // the header and the wrong one
    expect(within(cases).getByText('632001 41 08 209 000 · 502 000 / 321 000')).toBeVisible();
    await userEvent.click(screen.getByText('Všetky', { exact: true }));
    expect(within(cases).getAllByRole('row')).toHaveLength(3);

    await userEvent.click(screen.getByRole('button', { name: 'Prepočítať' }));
    await waitFor(() => {
      expect(api.calls.some((c) => c.path.includes('refresh=true'))).toBe(true);
    });
  });
});
