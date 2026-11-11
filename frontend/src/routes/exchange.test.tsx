import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { ImportPreview, ImportRun, Issue, Report } from '../features/exchange/api';
import { mockApi } from '../test/api';
import { nodeFile, nodeForms } from '../test/files';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Importy a exporty and the import wizard (P2-M3-T08): the history and the templates, the
// whole wizard from upload to apply, a run with hard errors that cannot be applied, the
// confirmation for errors against the global lists by keyboard, and the transforms dialog.

const base = `/api/customers/${BOLDOG.id}/imports`;
const NOW = '2026-11-09T10:00:00Z';

function run(id: string, overrides: Partial<ImportRun> = {}): ImportRun {
  return {
    id,
    customer_id: BOLDOG.id,
    import_type: 'accounts',
    year: 2026,
    state: 'uploaded',
    file: { name: 'rozvrh.csv', size: 120, format: 'csv' },
    created_at: NOW,
    created_by: 'u-jana',
    updated_at: NOW,
    options: null,
    mapping: null,
    template_id: null,
    report: null,
    job_id: null,
    applying: false,
    errors_confirmed: false,
    version_id: null,
    last_error: null,
    can_apply: false,
    ...overrides,
  };
}

const MAPPING = {
  import_type: 'accounts' as const,
  fields: {
    su: { column: 'Syntetický účet', constant: null, transforms: [] },
    au: { column: 'Analytický účet', constant: null, transforms: [] },
    type: { column: 'Druh účtu', constant: null, transforms: [] },
    description: { column: 'Názov', constant: null, transforms: [] },
  },
  skip_empty_key: true,
  duplicates: null,
  facts: [],
};

const PREVIEW: ImportPreview = {
  format: 'csv',
  sheets: [],
  sheet: null,
  encoding: 'windows-1250',
  delimiter: ';',
  header_row: 1,
  columns: [
    { key: 'Syntetický účet', header: 'Syntetický účet', letter: 'A' },
    { key: 'Analytický účet', header: 'Analytický účet', letter: 'B' },
    { key: 'Druh účtu', header: 'Druh účtu', letter: 'C' },
    { key: 'Názov', header: 'Názov', letter: 'D' },
  ],
  preamble: [],
  rows: [
    { number: 2, cells: ['518', '1', 'Nákladový', 'Telefóny'] },
    { number: 3, cells: ['321', '0', 'Pasívny', 'Dodávatelia'] },
  ],
  data_rows: 2,
  signature: 'abc',
  suggestion: MAPPING,
  template_id: null,
  template_name: null,
  fields: [
    { name: 'su', kind: 'code', required: true, key: true, line: false, derived: false },
    { name: 'au', kind: 'code', required: true, key: true, line: false, derived: false },
    { name: 'type', kind: 'account_type', required: true, key: false, line: false, derived: false },
    { name: 'activity', kind: 'text', required: false, key: false, line: false, derived: false },
    { name: 'description', kind: 'text', required: false, key: false, line: false, derived: false },
  ],
};

function issue(code: string, overrides: Partial<Issue> = {}): Issue {
  return {
    severity: 'error',
    code,
    message: `${code} in English`,
    rows: [],
    field: null,
    key: null,
    value: null,
    confirmable: false,
    ...overrides,
  };
}

function report(overrides: Partial<Report> = {}): Report {
  return {
    checked_at: NOW,
    rows_read: 2,
    entries: 2,
    errors: [],
    warnings: [],
    diff: {
      base_version_id: 'v1',
      base_number: 1,
      added: 1,
      removed: 0,
      changed: 0,
      unchanged: 1,
      added_sample: [{ su: '518', au: '001', type: 'cost', description: 'Telefóny' }],
      removed_sample: [],
      changed_sample: [],
    },
    preview: [{ su: '518', au: '001', type: 'cost', description: 'Telefóny' }],
    file_ico: null,
    period: null,
    counters: [],
    numbers_used: 0,
    ...overrides,
  };
}

describe('Importy a exporty', () => {
  it('lists the runs and the templates, with the actions the role has', async () => {
    mockApi({
      'GET /api/me': { body: meAs('user') },
      [`GET ${base}`]: {
        body: {
          items: [
            run('r1', { state: 'applied', report: report(), version_id: 'v2' }),
            run('r2', {
              state: 'dry_run_failed',
              import_type: 'budget_expense',
              report: report({ errors: [issue('not_a_number', { rows: [5] })] }),
            }),
          ],
          total: 2,
        },
      },
      [`GET /api/customers/${BOLDOG.id}/templates`]: {
        body: [
          {
            id: 't1',
            scope: 'customer',
            owner_id: BOLDOG.id,
            name: 'Boldog – rozvrh',
            import_type: 'accounts',
            signature: 'abc',
            mapping: MAPPING,
            builtin: false,
            created_at: NOW,
            updated_at: NOW,
          },
          {
            id: 'builtin:topset-chart',
            scope: 'builtin',
            owner_id: null,
            name: 'TOPSET – Účtový rozvrh',
            import_type: 'accounts',
            signature: 'def',
            mapping: MAPPING,
            builtin: true,
            created_at: NOW,
            updated_at: NOW,
          },
        ],
      },
    });
    await renderApp(`/c/${BOLDOG.id}/exchange`);
    const history = await screen.findByRole('region', { name: 'História importov' });
    const [, applied, failed] = within(history).getAllByRole('row') as [
      HTMLElement,
      HTMLElement,
      HTMLElement,
    ];
    expect(within(applied).getByText('Importovaný')).toBeInTheDocument();
    expect(within(applied).getByRole('link', { name: 'rozvrh.csv' })).toHaveAttribute(
      'href',
      `${base}/r1/file`,
    );
    expect(within(failed).getByText('Skúška s chybami')).toBeInTheDocument();
    expect(within(failed).getByText(/chyby 1/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Nový import' })).toBeInTheDocument();
    const templates = await screen.findByRole('region', { name: 'Šablóny mapovania' });
    expect(within(templates).getByText('Vstavaná')).toBeInTheDocument();
    expect(
      within(templates).getByRole('button', { name: 'Odstrániť šablónu Boldog – rozvrh' }),
    ).toBeInTheDocument();
    expect(
      within(templates).queryByRole('button', { name: /TOPSET – Účtový rozvrh/ }),
    ).not.toBeInTheDocument();
  });

  it('gives a viewer the history but neither imports nor templates', async () => {
    mockApi({
      'GET /api/me': { body: meAs('viewer') },
      [`GET ${base}`]: { body: { items: [], total: 0 } },
    });
    await renderApp(`/c/${BOLDOG.id}/exchange`);
    expect(await screen.findByText('Zatiaľ žiadny import.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Nový import' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Nový export' })).not.toBeInTheDocument();
    expect(screen.queryByText('Šablóny mapovania')).not.toBeInTheDocument();
  });

  it('starts a new export of the booked invoices not exported yet', async () => {
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('user') },
      [`GET ${base}`]: { body: { items: [], total: 0 } },
      [`GET /api/customers/${BOLDOG.id}/templates`]: { body: [] },
      [`GET /api/customers/${BOLDOG.id}/exports`]: { body: { items: [], total: 0 } },
      [`POST /api/customers/${BOLDOG.id}/exports/preview`]: {
        body: { invoices: 3, again: 0, skipped: 0 },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/exchange`);
    expect(await screen.findByText('Zatiaľ žiadny export.')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Nový export' }));
    const dialog = await screen.findByRole('dialog', { name: 'Export faktúr' });
    expect(await within(dialog).findByText('Zaúčtované faktúry do exportu: 3')).toBeVisible();
    const preview = calls.find((c) => c.path === `/api/customers/${BOLDOG.id}/exports/preview`);
    expect(preview?.body).toEqual({
      format: 'csv',
      filter: { state: ['booked'] },
      sort: 'booking_date',
    });
  });
});

describe('the import wizard', () => {
  it('uploads, reads, maps, checks and applies', async () => {
    let current = run('r1');
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('user') },
      [`POST ${base}`]: () => ({ status: 201, body: current }),
      [`GET ${base}/r1`]: () => ({ body: current }),
      [`GET ${base}/r1/preview`]: { body: PREVIEW },
      [`PUT ${base}/r1/mapping`]: () => {
        current = run('r1', { state: 'mapped', mapping: MAPPING });
        return { body: current };
      },
      [`POST ${base}/r1/dry-run`]: () => {
        current = run('r1', {
          state: 'dry_run_ok',
          mapping: MAPPING,
          report: report(),
          can_apply: true,
        });
        return { status: 202, body: current };
      },
      [`POST ${base}/r1/apply`]: () => {
        current = run('r1', {
          state: 'applied',
          mapping: MAPPING,
          report: report(),
          version_id: 'v2',
        });
        return { status: 202, body: current };
      },
      [`POST ${base}/r1/template`]: () => ({
        status: 201,
        body: { id: 't9', name: 'rozvrh', scope: 'customer' },
      }),
    });
    await nodeForms();
    const user = userEvent.setup();
    const { container } = await renderApp(`/c/${BOLDOG.id}/exchange/import?type=accounts`);
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error('no file input');
    await user.upload(input, nodeFile('rozvrh.csv', 'text/csv', 'SU;AU\n518;1\n'));
    await user.click(screen.getByRole('button', { name: 'Nahrať a pokračovať' }));
    await waitFor(() => {
      const upload = calls.find((c) => c.method === 'POST' && c.path === base);
      expect(upload?.body).toMatchObject({ import_type: 'accounts', file: 'rozvrh.csv' });
    });

    // Reading: the preview with the detected encoding and delimiter.
    const preview = await screen.findByRole('region', { name: 'Ukážka súboru' });
    expect(within(preview).getByText('Telefóny')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Pokračovať na mapovanie' }));

    // Mapping: the suggestion from the header names; each field has its source select.
    expect(await screen.findByText(/navrhnuté podľa názvov stĺpcov/)).toBeInTheDocument();
    const su = screen.getAllByLabelText('Zdroj hodnoty: SU (syntetický účet)')[0];
    expect(su).toHaveValue('A · Syntetický účet');
    await user.click(screen.getByRole('button', { name: 'Spustiť skúšobný import' }));
    const mapped = calls.find((c) => c.method === 'PUT');
    expect(mapped?.body).toMatchObject({
      options: { header_row: 1, delimiter: ';', encoding: 'windows-1250' },
      mapping: MAPPING,
    });

    // The report, then apply.
    expect(await screen.findByText('Bez chýb.')).toBeInTheDocument();
    expect(screen.getByText('Porovnané s aktívnou verziou 1.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Importovať' }));
    await waitFor(() => {
      expect(calls.find((c) => c.path === `${base}/r1/apply`)?.body).toEqual({
        confirm_errors: false,
      });
    });
    expect(await screen.findByText('Import je hotový')).toBeInTheDocument();

    // Save the mapping as the customer's template.
    await user.clear(screen.getByRole('textbox', { name: 'Názov šablóny' }));
    await user.type(screen.getByRole('textbox', { name: 'Názov šablóny' }), 'Boldog – rozvrh');
    await user.click(screen.getByRole('button', { name: 'Uložiť šablónu' }));
    await waitFor(() => {
      expect(calls.find((c) => c.path === `${base}/r1/template`)?.body).toEqual({
        scope: 'customer',
        name: 'Boldog – rozvrh',
      });
    });
  });

  it('refuses to apply a run with hard errors and words them in Slovak', async () => {
    const failed = run('r2', {
      state: 'dry_run_failed',
      mapping: MAPPING,
      report: report({
        errors: [issue('string_pattern_mismatch', { rows: [5], field: 'su', key: '5x8 003' })],
        warnings: [issue('missing_description', { severity: 'warning', rows: [3, 4] })],
      }),
    });
    mockApi({
      'GET /api/me': { body: meAs('user') },
      [`GET ${base}/r2`]: { body: failed },
      [`GET ${base}/r2/preview`]: { body: PREVIEW },
    });
    await renderApp(`/c/${BOLDOG.id}/exchange/import?run=r2`);
    const errors = await screen.findByRole('region', { name: 'Chyby skúšobného importu' });
    expect(within(errors).getByText('Hodnota nemá správny tvar.')).toBeInTheDocument();
    expect(within(errors).getByText('5x8 003')).toBeInTheDocument();
    expect(screen.getByText('Import sa nedá potvrdiť')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Importovať' })).toBeDisabled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('applies errors against the global lists only with the confirmation, by keyboard', async () => {
    const confirmable = run('r3', {
      import_type: 'budget_expense',
      state: 'dry_run_failed',
      mapping: { ...MAPPING, import_type: 'budget_expense', fields: {} },
      can_apply: true,
      report: report({
        errors: [
          issue('unknown_ek', { rows: [7], key: '999999 41 01 110 000', confirmable: true }),
        ],
      }),
    });
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('user') },
      [`GET ${base}/r3`]: { body: confirmable },
      [`GET ${base}/r3/preview`]: { body: PREVIEW },
      [`POST ${base}/r3/apply`]: {
        status: 202,
        body: { ...confirmable, applying: true, job_id: 'j1', errors_confirmed: true },
      },
    });
    const user = userEvent.setup();
    await renderApp(`/c/${BOLDOG.id}/exchange/import?run=r3`);
    const apply = await screen.findByRole('button', { name: 'Importovať' });
    expect(apply).toBeDisabled();
    const checkbox = screen.getByRole('checkbox', { name: /Importovať napriek 1 chybe/ });
    checkbox.focus();
    await user.keyboard(' ');
    expect(checkbox).toBeChecked();
    expect(apply).toBeEnabled();
    apply.focus();
    await user.keyboard('{Enter}');
    await waitFor(() => {
      expect(calls.find((c) => c.path === `${base}/r3/apply`)?.body).toEqual({
        confirm_errors: true,
      });
    });
    expect(await screen.findByText('Importuje sa…')).toBeInTheDocument();
  });

  it('edits a field’s transforms in a dialog the keyboard opens and closes', async () => {
    mockApi({
      'GET /api/me': { body: meAs('user') },
      [`GET ${base}/r4`]: { body: run('r4') },
      [`GET ${base}/r4/preview`]: { body: PREVIEW },
    });
    const user = userEvent.setup();
    await renderApp(`/c/${BOLDOG.id}/exchange/import?run=r4`);
    await user.click(await screen.findByRole('button', { name: 'Pokračovať na mapovanie' }));
    const edit = await screen.findByRole('button', {
      name: 'Upraviť – úpravy hodnoty poľa SU (syntetický účet)',
    });
    edit.focus();
    await user.keyboard('{Enter}');
    const dialog = await screen.findByRole('dialog', { name: /Úpravy hodnoty: SU/ });
    await user.click(within(dialog).getByRole('button', { name: 'Pridať' }));
    await user.click(within(dialog).getByRole('button', { name: 'Uložiť' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(screen.getAllByText('orezať medzery').length).toBeGreaterThan(0);
    // Escape closes the dialog without saving.
    edit.focus();
    await user.keyboard('{Enter}');
    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('is not for viewers', async () => {
    mockApi({ 'GET /api/me': { body: meAs('viewer') } });
    await renderApp(`/c/${BOLDOG.id}/exchange/import`);
    expect(await screen.findByText('Na túto stránku nemáte oprávnenie.')).toBeInTheDocument();
  });
});
