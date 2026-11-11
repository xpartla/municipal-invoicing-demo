import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi, type Call } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Kontrola údajov (P2-M5-T10, plan §8.5): the document viewer with the focused field's box,
// the note's crop with the suggestions, amber and red marks, the keyboard path (Enter
// confirms and goes on, Tab skips to the next doubtful field), "Potvrdiť" leading to the
// proposal on the same page; a file still being read, one that could not be read.

const base = `/api/customers/${BOLDOG.id}`;
const ID = 'inv-7';
const DOC = 'doc-7';

const FIELDS = {
  id: ID,
  supplier: {
    name: 'Slovak Telekom, a.s.',
    ico: '35763469',
    dic: null,
    ic_dph: null,
    iban: 'SK31 1200 0000 1987 4263 7541',
    address: null,
  },
  customer: { name: 'Obec Boldog', ico: '00305863' },
  invoice: {
    number: '8390051427',
    variable_symbol: '8390051427',
    issue_date: null,
    delivery_date: null,
    due_date: '2026-07-07',
    currency: 'EUR',
    document_type: 'invoice',
  },
  handwritten: { date: null, number: null },
  totals: { net: 78.09, vat: 15.62, gross: 93.71, vat_rates: [] },
  lines: [],
  free_text: [],
  ocr_meta: { synthetic: false, confidence: {} },
  intake: { channel: 'scan', format: null },
};

function invoice(overrides: object = {}) {
  return {
    id: ID,
    customer_id: BOLDOG.id,
    channel: 'scan',
    state: 'extracted',
    source_ref: null,
    document_id: DOC,
    fields: FIELDS,
    proposal: null,
    basis: null,
    coding_error: null,
    needs_review: false,
    booking: null,
    number: null,
    paid_on: null,
    uploaded_at: '2026-06-23T07:00:00Z',
    uploaded_by: 'u-user',
    checked_at: null,
    coded_at: null,
    booked_at: null,
    exported_at: null,
    paid_at: null,
    discarded_at: null,
    discard_reason: null,
    extraction_error: null,
    actions: ['check', 'discard'],
    ...overrides,
  };
}

const EXTRACTION = {
  id: 'ex-7',
  document_id: DOC,
  invoice_id: ID,
  engine: 'tesseract',
  engine_version: '5.5.3',
  source: 'ocr',
  created_at: '2026-06-23T07:00:05Z',
  duration_ms: 4200,
  pages: 2,
  warnings: ['supplier_ico_check_digit', 'addressed_to_another_entity'],
  confidence: {
    'supplier.name': 0.9,
    'supplier.ico': 0.9,
    'supplier.iban': 0.45,
    'invoice.number': 0.9,
    'invoice.variable_symbol': 0.9,
    'invoice.due_date': 0.9,
    'totals.gross': 0.9,
  },
  evidence: {
    'supplier.iban': { page: 0, box: [200, 900, 1000, 950] },
    'totals.gross': { page: 1, box: [1500, 2000, 1900, 2060] },
  },
  note: {
    page: 0,
    box: [1600, 40, 2300, 300],
    found: true,
    date: [
      { value: '2026-06-23', source: 'ocr', plausible: true, reasons: [] },
      { value: '2026-05-23', source: 'ocr', plausible: false, reasons: ['before_issue'] },
    ],
    number: [
      { value: '144', source: 'ocr', plausible: true, reasons: [] },
      { value: '223', source: 'counter', plausible: true, reasons: [] },
    ],
  },
  note_image: true,
  number_preview: null,
};

const CHECKED = invoice({
  state: 'ready',
  checked_at: '2026-06-23T07:10:00Z',
  coded_at: '2026-06-23T07:10:00Z',
  actions: ['check', 'recode', 'book', 'discard'],
  proposal: {
    invoice_id: ID,
    bundle_id: '00305863/2026-08',
    document: { series: 'FD', number: 'FD/144/26', booking_date: '2026-06-23' },
    supplier: { name: 'Slovak Telekom, a.s.', ico: '35763469', known: true },
    invoice: { number: '8390051427', gross: 93.71 },
    posting: [
      {
        md: '518 003',
        dal: '321 000',
        amount: 93.71,
        text: 'tel.poplatky',
        stredisko: null,
        transfer: null,
      },
    ],
    budget: [
      {
        key: '632005 41 01 110 000',
        ek: '632005',
        zdroj: '41',
        oddiel: '01',
        trieda: '110',
        analytika: '000',
        amount: 93.71,
        text: 'telefon,fax',
        stredisko: null,
        transfer: null,
      },
    ],
    confidence: { overall: 0.95 },
    evidence: [],
    alternatives: [],
    validation: { ok: true, checks: [], errors: [], warnings: [] },
    needs_review: false,
    review_reasons: [],
  },
});

function checkApi(current: () => object, extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /api/me': { body: meAs('user') },
    [`GET ${base}/invoices/${ID}`]: () => ({ body: current() }),
    [`GET ${base}/documents/${DOC}/extraction`]: { body: EXTRACTION },
    [`GET ${base}/invoices`]: { body: { items: [], total: 0 } },
    [`GET ${base}/number-series`]: { body: { year: 2026, items: [{ series: 'FD' }] } },
    [`GET ${base}/codelists/budget_expense/entries`]: {
      body: { version: null, items: [], total: 0 },
    },
    [`GET ${base}/codelists/accounts/entries`]: { body: { version: null, items: [], total: 0 } },
    ...extra,
  });
}

const posted = (calls: Call[], step: string) =>
  calls.filter((c) => c.method === 'POST' && c.path === `${base}/invoices/${ID}/${step}`);

/** The page image as loaded, at its natural size (jsdom loads no images). */
function loaded(image: HTMLElement, width = 2480, height = 3508) {
  Object.defineProperty(image, 'naturalWidth', { value: width, configurable: true });
  Object.defineProperty(image, 'naturalHeight', { value: height, configurable: true });
  fireEvent.load(image);
}

describe('the check step', () => {
  it('shows the document, the note and the marks, and highlights the focused field', async () => {
    checkApi(() => invoice());
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    expect(
      await screen.findByRole('tab', { name: 'Kontrola údajov', selected: true }),
    ).toBeVisible();
    const viewer = await screen.findByRole('region', { name: 'Doklad' });
    const page = within(viewer).getByRole('img', { name: 'Strana 1 dokladu' });
    expect(page).toHaveAttribute('src', `${base}/documents/${DOC}/pages/0`);
    expect(within(viewer).getByRole('radio', { name: 'Str. 2' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Rukou písaná poznámka/ })).toHaveAttribute(
      'src',
      `${base}/documents/${DOC}/note`,
    );
    expect(
      screen.getByText('Faktúra je adresovaná inému odberateľovi ako tomuto klientovi.'),
    ).toBeVisible();

    // Amber: read with doubt, a failed check, the handwritten fields; red: empty required.
    const iban = await screen.findByLabelText('IBAN');
    expect(iban).toHaveAttribute('data-check', 'doubtful');
    expect(iban).toHaveAccessibleDescription('Prečítané s nízkou istotou; skontrolujte.');
    expect(screen.getByLabelText('IČO')).toHaveAccessibleDescription(
      'Kontrolná číslica IČO nesedí; skontrolujte.',
    );
    expect(screen.getByLabelText('Dátum zaúčtovania (rukou)')).toHaveAttribute(
      'data-check',
      'doubtful',
    );
    expect(screen.getByLabelText('Číslo faktúry')).not.toHaveAttribute('data-check');
    expect(screen.getByLabelText(/^Dátum vystavenia/)).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText(/^Dátum dodania/)).toHaveAttribute('aria-invalid', 'true');

    // The focused field's box on its page (the totals are on page 2).
    loaded(page);
    fireEvent.focus(iban);
    const box = await within(viewer).findByTestId('viewer-highlight');
    expect(parseFloat(box.style.left)).toBeCloseTo((200 / 2480) * 100, 3);
    fireEvent.focus(screen.getByLabelText(/^Spolu na úhradu/));
    await waitFor(() => {
      expect(within(viewer).getByRole('radio', { name: 'Str. 2' })).toBeChecked();
    });
    expect(within(viewer).getByRole('img', { name: 'Strana 2 dokladu' })).toHaveAttribute(
      'src',
      `${base}/documents/${DOC}/pages/1`,
    );

    // Zooming.
    const user = userEvent.setup();
    await user.click(within(viewer).getByRole('button', { name: 'Priblížiť' }));
    expect(within(viewer).getByText('150 %')).toBeVisible();
    await user.click(within(viewer).getByRole('button', { name: 'Prispôsobiť šírke' }));
    expect(within(viewer).getByText('100 %')).toBeVisible();
  });

  it('goes field by field with the keyboard, confirms and shows the proposal', async () => {
    let current: object = invoice();
    const { calls } = checkApi(() => current, {
      [`POST ${base}/invoices/${ID}/check`]: () => {
        current = CHECKED;
        return { body: CHECKED };
      },
    });
    const user = userEvent.setup();
    const { router } = await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    const date = await screen.findByLabelText('Dátum zaúčtovania (rukou)');
    await screen.findByRole('group', { name: /Návrhy pre Dátum zaúčtovania/ });

    // Enter on the empty handwritten date takes its first suggestion and goes on.
    await user.click(date);
    await user.keyboard('{Enter}');
    expect(date).toHaveValue('2026-06-23');
    expect(date).not.toHaveAttribute('data-check');
    const number = screen.getByLabelText('Poradové číslo dokladu (rukou)');
    expect(number).toHaveFocus();
    // A suggestion can be picked instead: the counter's number.
    await user.click(screen.getByRole('button', { name: '223 · z počítadla' }));
    expect(number).toHaveValue('223');
    await user.clear(number);
    await user.type(number, '144');

    // Tab skips the sure fields: from the number to the doubtful IČO.
    await user.click(number);
    await user.tab();
    const ico = screen.getByLabelText('IČO');
    expect(ico).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(ico).not.toHaveAttribute('data-check');
    const iban = screen.getByLabelText('IBAN');
    expect(iban).toHaveFocus();
    await user.keyboard('{Enter}');
    // Then the empty required issue date.
    const issued = screen.getByLabelText(/^Dátum vystavenia/);
    expect(issued).toHaveFocus();
    await user.type(issued, '2026-06-22');
    await user.tab();
    const supplied = screen.getByLabelText(/^Dátum dodania/);
    expect(supplied).toHaveFocus();
    // The invoice prints no date of supply: the issue date stands in.
    await user.click(screen.getByLabelText('Na faktúre nie je, platí dátum vystavenia'));
    expect(supplied).toBeDisabled();
    expect(supplied).not.toHaveAttribute('aria-invalid', 'true');
    await user.click(issued);
    await user.keyboard('{Enter}');
    expect(screen.getByRole('button', { name: 'Potvrdiť' })).toHaveFocus();
    expect(posted(calls, 'check')).toHaveLength(0);

    await user.keyboard('{Enter}');
    await waitFor(() => {
      expect(posted(calls, 'check')).toHaveLength(1);
    });
    expect(posted(calls, 'check')[0]?.body).toMatchObject({
      supplier: {
        name: 'Slovak Telekom, a.s.',
        ico: '35763469',
        iban: 'SK31 1200 0000 1987 4263 7541',
      },
      invoice: { issue_date: '2026-06-22', delivery_date: null, due_date: '2026-07-07' },
      handwritten: { date: '2026-06-23', number: '144' },
      totals: { gross: 93.71 },
      ocr_meta: { confidence: {} },
    });
    expect(
      await screen.findByRole('tab', { name: 'Návrh a zaúčtovanie', selected: true }),
    ).toBeVisible();
    expect(router.state.location.search).toMatchObject({ tab: 'proposal' });
    expect(await screen.findByText('Zaúčtovanie záväzku')).toBeVisible();
  });

  it('walks on to the next uploaded invoice to check', async () => {
    checkApi(() => CHECKED);
    const user = userEvent.setup();
    const { router } = await renderApp(
      `/c/${BOLDOG.id}/invoices/${ID}?tab=proposal&queue=inv-8,inv-9`,
    );
    await user.click(await screen.findByRole('button', { name: 'Ďalšia na kontrolu (2)' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/c/${BOLDOG.id}/invoices/inv-8`);
    });
    expect(router.state.location.search).toEqual({ tab: 'check', queue: 'inv-9' });
  });

  it('waits while the file is read', async () => {
    let polls = 0;
    checkApi(() => {
      polls += 1;
      return invoice(polls > 1 ? {} : { state: 'extracting', fields: null, actions: ['discard'] });
    });
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    expect(await screen.findByText('Súbor sa číta…')).toBeVisible();
    expect(await screen.findByLabelText('IBAN', {}, { timeout: 4000 })).toBeVisible();
  }, 8000);

  it('says why a file could not be read, reads it again or takes the fields by hand', async () => {
    const failed = invoice({
      state: 'extraction_failed',
      fields: null,
      extraction_error: 'too_many_pixels',
      actions: ['discard'],
    });
    const { calls } = checkApi(() => failed, {
      [`GET ${base}/documents/${DOC}/extraction`]: {
        status: 404,
        body: { code: 'not_found', detail: 'x' },
      },
      [`POST ${base}/invoices/${ID}/extraction`]: { status: 202, body: { job_id: 'j1' } },
      [`POST ${base}/invoices/${ID}/manual`]: { body: CHECKED },
    });
    const user = userEvent.setup();
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    expect(await screen.findByText('Obrázok je príliš veľký na prečítanie.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Stiahnuť súbor' })).toHaveAttribute(
      'href',
      `${base}/documents/${DOC}/file`,
    );
    await user.click(screen.getByRole('button', { name: 'Prečítať znova' }));
    await waitFor(() => {
      expect(posted(calls, 'extraction')).toHaveLength(1);
    });

    await user.type(screen.getByLabelText(/^Názov/), 'Slovak Telekom, a.s.');
    await user.type(screen.getByLabelText(/^Dátum vystavenia/), '2026-06-22');
    await user.type(screen.getByLabelText(/^Dátum dodania/), '2026-06-21');
    await user.type(screen.getByLabelText(/^Spolu na úhradu/), '93,71');
    await user.click(screen.getByRole('button', { name: 'Uložiť a navrhnúť' }));
    await waitFor(() => {
      expect(posted(calls, 'manual')).toHaveLength(1);
    });
    expect(posted(calls, 'manual')[0]?.body).toMatchObject({
      supplier: { name: 'Slovak Telekom, a.s.' },
      invoice: { issue_date: '2026-06-22', delivery_date: '2026-06-21' },
      totals: { gross: 93.71 },
    });
  });
});
