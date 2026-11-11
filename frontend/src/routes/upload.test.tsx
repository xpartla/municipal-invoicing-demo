import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { nodeFile, nodeForms } from '../test/files';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Nová faktúra's upload (P2-M5-T09, plan §10.5): several files at once, each with its
// progress (uploading, reading, ready to check, failed with the reason), a duplicate linking
// the first invoice, and "Pokračovať na kontrolu" walking through the ready ones.

const base = `/api/customers/${BOLDOG.id}`;

function invoice(id: string, state: string, extra: object = {}) {
  return { id, customer_id: BOLDOG.id, state, channel: 'scan', extraction_error: null, ...extra };
}

function accepted(name: string, id: string) {
  return {
    filename: name,
    status: 'accepted',
    document_id: `doc-${id}`,
    invoice_id: id,
    job_id: `job-${id}`,
    reason: null,
    message: null,
    duplicate_of: null,
  };
}

function file(name: string, type = 'image/jpeg') {
  return nodeFile(name, type);
}

async function openUpload() {
  await nodeForms();
  const user = userEvent.setup();
  const rendered = await renderApp(`/c/${BOLDOG.id}/invoices/new`);
  await screen.findByRole('heading', { level: 1, name: 'Nová faktúra' });
  return { user, ...rendered };
}

describe('uploading invoices', () => {
  it('uploads several files and shows each one reading, then ready to check', async () => {
    let polls = 0;
    const { calls } = mockApi({
      'GET /api/me': { body: meAs('user') },
      [`POST ${base}/documents`]: {
        body: {
          accepted: 2,
          rejected: 1,
          items: [
            accepted('a.jpg', 'inv-a'),
            accepted('b.pdf', 'inv-b'),
            {
              ...accepted('c.png', 'x'),
              status: 'rejected',
              document_id: 'doc-old',
              invoice_id: null,
              job_id: null,
              reason: 'duplicate',
              message: 'the same file was uploaded before',
              duplicate_of: 'inv-old',
            },
          ],
        },
      },
      [`GET ${base}/invoices/inv-a`]: () => {
        polls += 1;
        return { body: invoice('inv-a', polls > 1 ? 'extracted' : 'extracting') };
      },
      [`GET ${base}/invoices/inv-b`]: { body: invoice('inv-b', 'extracted') },
    });
    const { user, router } = await openUpload();
    const zone = screen.getByRole('region', { name: 'Nahrávanie faktúr' });
    expect(within(zone).getByText(/najviac 20 MB a 5 strán/)).toBeVisible();
    await user.upload(screen.getByLabelText('Vybrať súbory'), [
      file('a.jpg'),
      file('b.pdf', 'application/pdf'),
      file('c.png', 'image/png'),
    ]);

    const table = await screen.findByRole('table', { name: 'Nahrané súbory' });
    const post = calls.find((c) => c.method === 'POST');
    expect(post?.body).toEqual({ files: ['a.jpg', 'b.pdf', 'c.png'] });
    const row = (name: string) => within(table).getByRole('row', { name: new RegExp(name) });
    await waitFor(() => {
      expect(within(row('b.pdf')).getByText('Na kontrolu')).toBeVisible();
    });
    expect(within(row('c.png')).getByText('Odmietnutý')).toBeVisible();
    expect(within(row('c.png')).getByText('Rovnaký súbor už bol nahraný.')).toBeVisible();
    expect(
      within(row('c.png')).getByRole('link', { name: 'Otvoriť faktúru z rovnakého súboru' }),
    ).toHaveAttribute('href', `/c/${BOLDOG.id}/invoices/inv-old`);
    // a.jpg was still being read at first, then became ready (polled every two seconds).
    await waitFor(
      () => {
        expect(within(row('a.jpg')).getByText('Na kontrolu')).toBeVisible();
      },
      { timeout: 5000 },
    );
    expect(within(row('a.jpg')).getByRole('link', { name: 'Skontrolovať' })).toHaveAttribute(
      'href',
      `/c/${BOLDOG.id}/invoices/inv-a?tab=check`,
    );

    await user.click(screen.getByRole('button', { name: 'Pokračovať na kontrolu (2)' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/c/${BOLDOG.id}/invoices/inv-a`);
    });
    expect(router.state.location.search).toEqual({ tab: 'check', queue: 'inv-b' });
  }, 10000);

  it('says why a file was refused or could not be read', async () => {
    mockApi({
      'GET /api/me': { body: meAs('user') },
      [`POST ${base}/documents`]: {
        body: {
          accepted: 1,
          rejected: 1,
          items: [
            {
              ...accepted('faktura.pdf', 'x'),
              status: 'rejected',
              document_id: null,
              invoice_id: null,
              job_id: null,
              reason: 'file_type',
            },
            accepted('rozmazany.jpg', 'inv-f'),
          ],
        },
      },
      [`GET ${base}/invoices/inv-f`]: {
        body: invoice('inv-f', 'extraction_failed', { extraction_error: 'unreadable' }),
      },
    });
    const { user } = await openUpload();
    await user.upload(screen.getByLabelText('Vybrať súbory'), [
      // Named a PDF, its content is not one: the server refuses it by what it holds.
      file('faktura.pdf', 'application/pdf'),
      file('rozmazany.jpg'),
    ]);
    const table = await screen.findByRole('table', { name: 'Nahrané súbory' });
    expect(await within(table).findByText('Nie je to PDF, JPG, PNG, TIFF ani XML.')).toBeVisible();
    expect(await within(table).findByText('Súbor sa nedá otvoriť.')).toBeVisible();
    expect(within(table).getByText('Neprečítaný')).toBeVisible();
    expect(within(table).getByRole('link', { name: 'Otvoriť' })).toHaveAttribute(
      'href',
      `/c/${BOLDOG.id}/invoices/inv-f?tab=check`,
    );
    expect(screen.getByRole('button', { name: 'Pokračovať na kontrolu (0)' })).toBeDisabled();
  });

  it('offers a photo from the camera and manual entry', async () => {
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    await openUpload();
    const camera = screen.getByLabelText('Odfotiť faktúru');
    expect(camera).toHaveAttribute('capture', 'environment');
    expect(camera).toHaveAttribute('accept', 'image/*');
    expect(screen.getByRole('tab', { name: 'Zadať ručne' })).toBeVisible();
  });
});
