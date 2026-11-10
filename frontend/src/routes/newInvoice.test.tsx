import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Number series under Systém and manual entry (P2-M4-T09): the counters with their used
// numbers and gaps and the audited edit; the field form with its required fields, the pasted
// JSON and the API's field errors, then the invoice's detail.

const base = `/api/customers/${BOLDOG.id}`;

const FD = {
  series: 'FD',
  year: 2026,
  pattern: 'FD/XXX/RR',
  last_used: 222,
  last_used_number: 'FD/222/26',
  next_number: 'FD/223/26',
  used: [
    { number: 'FD/144/26', sequence: 144, kind: 'booked', invoice_id: 'i1', frozen: false },
    { number: 'FD/183/26', sequence: 183, kind: 'external', invoice_id: null, frozen: true },
  ],
  gaps: ['FD/145/26', 'FD/146/26'],
  stored: true,
};
const FDSJ = {
  ...FD,
  series: 'FDŠJ',
  pattern: 'FDŠJ/XXX/RR',
  last_used: 0,
  last_used_number: null,
  next_number: 'FDŠJ/001/26',
  used: [],
  gaps: [],
  stored: false,
};

function systemApi(role: 'user' | 'viewer', extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /api/me': { body: meAs(role) },
    [`GET ${base}/codelists`]: { body: { year: 2026, years: [2026], lists: [] } },
    [`GET ${base}/number-series`]: { body: { year: 2026, items: [FD, FDSJ] } },
    ...extra,
  });
}

async function openSeries() {
  const user = userEvent.setup();
  await renderApp(`/c/${BOLDOG.id}/system`);
  await user.click(await screen.findByRole('tab', { name: 'Číselné rady' }));
  await screen.findByRole('region', { name: 'Číselné rady' });
  return user;
}

describe('the number series under Systém', () => {
  it('shows the counters, the used numbers and the gaps', async () => {
    systemApi('viewer');
    const user = await openSeries();
    const fd = screen.getByRole('cell', { name: 'FD/222/26' }).closest('tr');
    if (!fd) throw new Error('no FD row');
    expect(fd).toHaveTextContent('FD/223/26');
    expect(fd).toHaveTextContent('FD/145/26, FD/146/26');
    expect(screen.getByText('bez medzier')).toBeVisible();
    expect(screen.queryByRole('button', { name: /Upraviť počítadlo/ })).toBeNull();
    await user.click(
      screen.getByRole('button', { name: 'Počet: 2 – zobraziť použité čísla radu FD' }),
    );
    const dialog = await screen.findByRole('dialog', { name: 'Použité čísla radu FD' });
    expect(dialog).toHaveTextContent('FD/144/26zaúčtovaná faktúra');
    expect(dialog).toHaveTextContent('FD/183/26z importu alebo z účtovného programunemenné');
  });

  it('edits a counter, refusing one below a used number', async () => {
    let attempts = 0;
    const { calls } = systemApi('user', {
      [`PUT ${base}/number-series/FD/2026`]: () =>
        ++attempts === 1
          ? {
              status: 422,
              body: {
                code: 'validation_failed',
                detail: [{ loc: ['body', 'last_used'], msg: 'x', type: 'below_used' }],
              },
            }
          : { body: { ...FD, last_used: 230, next_number: 'FD/231/26' } },
    });
    const user = await openSeries();
    await user.click(screen.getByRole('button', { name: 'Upraviť počítadlo radu FD' }));
    const dialog = await screen.findByRole('dialog', { name: 'Počítadlo radu FD v roku 2026' });
    const input = within(dialog).getByLabelText('Posledné použité poradové číslo');
    await user.clear(input);
    await user.type(input, '100');
    await user.click(within(dialog).getByRole('button', { name: 'Uložiť' }));
    expect(
      await within(dialog).findByText(
        'Počítadlo nemôže byť nižšie ako najvyššie použité číslo radu.',
      ),
    ).toBeVisible();
    await user.clear(input);
    await user.type(input, '230');
    await user.click(within(dialog).getByRole('button', { name: 'Uložiť' }));
    const toast = (await screen.findByText('Počítadlo je upravené.')).closest('[role="alert"]');
    if (!(toast instanceof HTMLElement)) throw new Error('no toast');
    expect(within(toast).getByRole('button', { name: 'Zavrieť' })).toBeVisible();
    const puts = calls.filter((c) => c.method === 'PUT');
    expect(puts.map((c) => c.body)).toEqual([{ last_used: 100 }, { last_used: 230 }]);
    expect(puts[0]?.path).toBe(`${base}/number-series/FD/2026`);
  });
});

function entryApi(extra: Parameters<typeof mockApi>[0] = {}) {
  return mockApi({
    'GET /api/me': { body: meAs('user') },
    [`GET ${base}/invoices/new-1`]: { status: 404, body: { code: 'not_found', detail: 'x' } },
    ...extra,
  });
}

describe('manual entry', () => {
  it('asks for the required fields, then sends the invoice and opens it', async () => {
    const user = userEvent.setup();
    const { calls } = entryApi({
      [`POST ${base}/invoices`]: { status: 201, body: { id: 'new-1' } },
    });
    const { router } = await renderApp(`/c/${BOLDOG.id}/invoices/new`);
    await screen.findByRole('heading', { level: 1, name: 'Nová faktúra' });
    await user.click(screen.getByRole('tab', { name: 'Zadať ručne' }));
    await user.click(screen.getByRole('button', { name: 'Uložiť a navrhnúť' }));
    expect(await screen.findAllByText('Toto pole je povinné.')).toHaveLength(3);
    expect(calls.some((c) => c.method === 'POST')).toBe(false);

    await user.type(screen.getByLabelText('Dátum zaúčtovania (rukou)'), '2026-06-23');
    await user.type(screen.getByLabelText(/Poradové číslo dokladu/), '144');
    await user.type(screen.getByLabelText(/^Názov/), 'Slovak Telekom, a.s.');
    await user.type(screen.getByLabelText('IČO'), '35763469');
    await user.type(screen.getByLabelText(/^Dátum vystavenia/), '2026-06-22');
    await user.type(screen.getByLabelText(/^Spolu na úhradu/), '93,71');
    await user.click(screen.getByRole('button', { name: 'Pridať položku' }));
    await user.type(screen.getByLabelText('Popis položky 1'), 'Poplatky');
    await user.type(screen.getByLabelText('Suma položky 1'), '93,71');
    await user.click(screen.getByRole('button', { name: 'Uložiť a navrhnúť' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/c/${BOLDOG.id}/invoices/new-1`);
    });
    const post = calls.find((c) => c.method === 'POST');
    expect(post?.body).toMatchObject({
      id: 'new',
      supplier: { name: 'Slovak Telekom, a.s.', ico: '35763469' },
      customer: { name: BOLDOG.name, ico: BOLDOG.ico },
      invoice: { issue_date: '2026-06-22', document_type: 'invoice', currency: 'EUR' },
      handwritten: { date: '2026-06-23', number: '144' },
      totals: { gross: 93.71 },
      lines: [{ description: 'Poplatky', gross: 93.71 }],
    });
  });

  it('fills the form from a pasted JSON and shows the API field errors', async () => {
    const user = userEvent.setup();
    entryApi({
      [`POST ${base}/invoices`]: {
        status: 422,
        body: {
          code: 'validation_failed',
          detail: [
            {
              loc: ['body', 'invoice', 'due_date'],
              msg: 'Input should be a valid date',
              type: 'date_from_datetime_parsing',
            },
          ],
        },
      },
    });
    await renderApp(`/c/${BOLDOG.id}/invoices/new`);
    await user.click(await screen.findByRole('tab', { name: 'Zadať ručne' }));
    await user.click(await screen.findByRole('button', { name: 'Vložiť JSON' }));
    const dialog = await screen.findByRole('dialog', { name: 'Vložiť faktúru ako JSON' });
    const area = within(dialog).getByLabelText('JSON faktúry');
    await user.click(area);
    await user.paste('{"oops":');
    await user.click(within(dialog).getByRole('button', { name: 'Vyplniť formulár' }));
    expect(await within(dialog).findByText('Text nie je platný JSON faktúry.')).toBeVisible();
    await user.clear(area);
    await user.paste(
      JSON.stringify({
        supplier: { name: 'ZSE Energia, a.s.', ico: '36677281' },
        invoice: { number: '42', issue_date: '2026-06-20', due_date: '2026-07-05' },
        handwritten: { date: '2026-06-21', number: '250' },
        totals: { gross: 150.5 },
        lines: [{ description: 'Elektrina', gross: 150.5 }],
      }),
    );
    await user.click(within(dialog).getByRole('button', { name: 'Vyplniť formulár' }));
    await waitFor(() => {
      expect(screen.getByLabelText(/^Názov/)).toHaveValue('ZSE Energia, a.s.');
    });
    expect(screen.getByLabelText(/^Spolu na úhradu/)).toHaveValue('150,50');
    expect(screen.getByLabelText('Popis položky 1')).toHaveValue('Elektrina');
    await user.click(screen.getByRole('button', { name: 'Uložiť a navrhnúť' }));
    const due = screen.getByLabelText('Dátum splatnosti');
    await waitFor(() => {
      expect(due).toHaveAttribute('aria-invalid', 'true');
    });
  });

  it('is not offered to a viewer', async () => {
    mockApi({ 'GET /api/me': { body: meAs('viewer') } });
    await renderApp(`/c/${BOLDOG.id}/invoices/new`);
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(
      'Prístup zamietnutý',
    );
  });
});
