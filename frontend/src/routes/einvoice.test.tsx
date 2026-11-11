import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi, type Call } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// The e-invoice in the check step (P2-M6-T06, plan §8.4, §8.5, decision 65): the viewer
// renders the invoice from its XML and shows the raw XML as text; the booking date is
// suggested as the upload date and confirmed, the number is left to the booking with a
// preview; a file that is no e-invoice shows its text and why.

const base = `/api/customers/${BOLDOG.id}`;
const ID = 'inv-e';
const DOC = 'doc-e';

const FIELDS = {
  id: ID,
  supplier: {
    name: 'HORNBACH Baumarkt SK spol. s r.o.',
    ico: '35838949',
    dic: '2021651470',
    ic_dph: 'SK2021651470',
    iban: 'SK95 0900 0000 0001 7612 4588',
    address: 'Galvaniho 9, 821 04 Bratislava',
    vat_payer: true,
  },
  customer: { name: 'Obec Boldog', ico: '00305863' },
  invoice: {
    number: '2026-418-019944',
    variable_symbol: '2026418019',
    issue_date: '2026-08-24',
    delivery_date: '2026-08-24',
    due_date: '2026-09-07',
    currency: 'EUR',
    document_type: 'invoice',
  },
  handwritten: { date: null, number: null },
  totals: { net: 327.98, vat: 75.44, gross: 403.42, vat_rates: [23] },
  lines: [
    {
      description: 'Farba fasádna biela 10 l',
      quantity: 4,
      unit: 'ks',
      unit_price: 32.49,
      net: 129.96,
      vat_rate: 23,
      vat: null,
      gross: null,
    },
  ],
  free_text: ['Ďakujeme za nákup.'],
  ocr_meta: { synthetic: false, confidence: { 'supplier.ico': 1, 'totals.gross': 1 } },
  intake: { channel: 'einvoice', format: 'ubl' },
};

function invoice(overrides: object = {}) {
  return {
    id: ID,
    customer_id: BOLDOG.id,
    channel: 'einvoice',
    state: 'extracted',
    source_ref: 'faktura.xml',
    document_id: DOC,
    fields: FIELDS,
    proposal: null,
    basis: null,
    coding_error: null,
    needs_review: false,
    booking: null,
    number: null,
    paid_on: null,
    uploaded_at: '2026-08-25T07:00:00Z',
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
  id: 'ex-e',
  document_id: DOC,
  invoice_id: ID,
  engine: 'ubl',
  engine_version: '2.1',
  source: 'einvoice',
  created_at: '2026-08-25T07:00:01Z',
  duration_ms: 40,
  pages: 0,
  warnings: ['iban_check_digits', 'missing_due_date'],
  confidence: { 'supplier.ico': 1, 'totals.gross': 1 },
  evidence: {},
  note: {
    page: 0,
    box: [0, 0, 0, 0],
    found: false,
    date: [{ value: '2026-08-25', source: 'upload', plausible: true, reasons: [] }],
    number: [],
  },
  note_image: false,
  number_preview: 46,
};

const XML =
  '<?xml version="1.0"?>\n<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">' +
  '<cbc:Note>&lt;script&gt;alert(1)&lt;/script&gt;</cbc:Note></Invoice>';

const VIEW = {
  format: 'ubl_invoice',
  family: 'ubl',
  version: '2.1',
  profile: 'urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0',
  attachment: null,
  document: FIELDS,
  customer_address: null,
  taxes: [{ category: 'S', rate: 23, taxable: 327.98, tax: 75.44 }],
  payable: 403.42,
  schema_errors: ["line 12: Element 'cbc:Foo': This element is not expected."],
  failure: null,
  xml: XML.replace('&lt;script&gt;alert(1)&lt;/script&gt;', '<script>alert(1)</script>'),
  truncated: false,
};

function api(extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /api/me': { body: meAs('user') },
    [`GET ${base}/invoices/${ID}`]: { body: invoice() },
    [`GET ${base}/documents/${DOC}/extraction`]: { body: EXTRACTION },
    [`GET ${base}/documents/${DOC}/einvoice`]: { body: VIEW },
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

describe('an e-invoice in the check step', () => {
  it('renders the invoice from its XML and marks the focused field', async () => {
    api();
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    const viewer = await screen.findByRole('region', { name: 'Elektronická faktúra' });
    expect(await within(viewer).findByText('UBL 2.1 (Peppol)')).toBeVisible();
    expect(within(viewer).getByRole('heading', { name: /Faktúra 2026-418-019944/ })).toBeVisible();
    expect(within(viewer).getByText('HORNBACH Baumarkt SK spol. s r.o.')).toBeVisible();
    expect(within(viewer).getByText('Farba fasádna biela 10 l')).toBeVisible();
    expect(within(viewer).getByText('Súbor nezodpovedá schéme UBL 2.1 (Peppol)')).toBeVisible();
    expect(within(viewer).queryByRole('tab', { name: 'PDF' })).toBeNull();
    // No scan, so no page image and no note's crop.
    expect(screen.queryByRole('img')).toBeNull();
    expect(
      screen.getByText('Údaje z elektronickej faktúry, ako ich poslal dodávateľ.'),
    ).toBeVisible();
    expect(screen.getByText('Faktúra neuvádza dátum splatnosti.')).toBeVisible();

    // The IBAN failed its check: amber in the form; focusing it marks it in the view.
    const iban = await screen.findByLabelText('IBAN');
    expect(iban).toHaveAccessibleDescription('Kontrolné číslice IBAN nesedia; skontrolujte.');
    fireEvent.focus(iban);
    await waitFor(() => {
      expect(viewer.querySelector('[data-field="supplier.iban"]')).toHaveAttribute(
        'data-focused',
        'true',
      );
    });
  });

  it('shows the raw XML as text', async () => {
    api();
    const user = userEvent.setup();
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    const viewer = await screen.findByRole('region', { name: 'Elektronická faktúra' });
    await user.click(await within(viewer).findByRole('tab', { name: 'XML' }));
    const raw = await within(viewer).findByRole('region', { name: 'Obsah súboru XML' });
    expect(raw).toHaveTextContent('<script>alert(1)</script>');
    expect(document.querySelector('script')).toBeNull();
  });

  it('suggests the upload date, leaves the number to the booking and confirms', async () => {
    let current: object = invoice();
    const { calls } = api({
      [`GET ${base}/invoices/${ID}`]: () => ({ body: current }),
      [`POST ${base}/invoices/${ID}/check`]: () => {
        current = invoice({ state: 'needs_review', checked_at: '2026-08-25T07:05:00Z' });
        return { body: current };
      },
    });
    const user = userEvent.setup();
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    const date = await screen.findByLabelText('Dátum zaúčtovania');
    expect(date).toHaveAttribute('data-check', 'doubtful');
    expect(date).toHaveAccessibleDescription(
      'Navrhnutý je deň nahratia faktúry; potvrďte dátum zaúčtovania.',
    );
    const number = screen.getByLabelText('Poradové číslo dokladu');
    expect(number).not.toHaveAttribute('data-check');
    expect(number).toHaveAccessibleDescription(/teraz by to bolo 46/);
    expect(screen.getByRole('button', { name: /25\.\s8\.\s2026 · deň nahratia/ })).toBeVisible();

    // Enter takes the suggested date; the number stays empty and is not asked for.
    await user.click(date);
    await user.keyboard('{Enter}');
    expect(date).toHaveValue('2026-08-25');
    expect(number).toHaveValue('');
    await user.click(screen.getByRole('button', { name: 'Potvrdiť' }));
    await waitFor(() => {
      expect(posted(calls, 'check')).toHaveLength(1);
    });
    expect(posted(calls, 'check')[0]?.body).toMatchObject({
      handwritten: { date: '2026-08-25', number: null },
    });
  });

  it('shows the PDF pages of an ISDOC PDF in their own tab', async () => {
    api({
      [`GET ${base}/documents/${DOC}/extraction`]: {
        body: { ...EXTRACTION, engine: 'isdoc', engine_version: '6.0.2', pages: 1 },
      },
      [`GET ${base}/documents/${DOC}/einvoice`]: {
        body: {
          ...VIEW,
          format: 'isdoc',
          family: 'isdoc',
          version: '6.0.2',
          profile: null,
          attachment: '2026-418-019944.isdoc',
          schema_errors: [],
        },
      },
    });
    const user = userEvent.setup();
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    const viewer = await screen.findByRole('region', { name: 'Elektronická faktúra' });
    expect(await within(viewer).findByText('ISDOC 6.0.2')).toBeVisible();
    expect(within(viewer).getByText('Príloha PDF: 2026-418-019944.isdoc')).toBeVisible();
    await user.click(within(viewer).getByRole('tab', { name: 'PDF' }));
    expect(await within(viewer).findByRole('img', { name: 'Strana 1 dokladu' })).toHaveAttribute(
      'src',
      `${base}/documents/${DOC}/pages/0`,
    );
  });

  it('says why an XML file is no e-invoice and shows its text', async () => {
    api({
      [`GET ${base}/invoices/${ID}`]: {
        body: invoice({
          state: 'extraction_failed',
          fields: null,
          extraction_error: 'einvoice_unknown',
          actions: ['discard'],
        }),
      },
      [`GET ${base}/documents/${DOC}/extraction`]: {
        status: 404,
        body: { code: 'not_found', detail: 'x' },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/invoices/${ID}`);
    expect(
      await screen.findByText('Súbor XML nie je faktúra vo formáte UBL ani ISDOC.'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Uložiť a navrhnúť' })).toBeVisible();
  });
});
