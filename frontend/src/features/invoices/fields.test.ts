import { describe, expect, it } from 'vitest';

import { documentOf, emptyValues, valuesOf } from './fields';

// The field form's values and the InvoiceDocument (P2-M4-T09).

const CUSTOMER = { name: 'Obec Boldog', ico: '00305863' };

describe('the field form and the InvoiceDocument', () => {
  it('turns typed values into the document the API takes', () => {
    const values = emptyValues();
    values.handwritten = { date: '2026-06-23', number: '144' };
    values.supplier.name = ' Slovak Telekom, a.s. ';
    values.supplier.ico = '35763469';
    values.invoice.issue_date = '2026-06-22';
    values.totals.gross = '93,71';
    values.lines = [
      { description: 'Poplatky', gross: '83,71' },
      { description: '  ', gross: '1' },
    ];
    values.notes = 'Za obdobie 5/2026\n\n';
    const document = documentOf(values, CUSTOMER);
    expect(document).toMatchObject({
      id: 'new',
      supplier: { name: 'Slovak Telekom, a.s.', ico: '35763469', dic: null },
      customer: CUSTOMER,
      invoice: { issue_date: '2026-06-22', delivery_date: null, document_type: 'invoice' },
      handwritten: { date: '2026-06-23', number: '144' },
      totals: { gross: 93.71, net: null, vat: null, vat_rates: [] },
      lines: [{ description: 'Poplatky', gross: 83.71 }],
      free_text: ['Za obdobie 5/2026'],
    });
  });

  it('reads an InvoiceDocument back into the form', () => {
    const values = valuesOf({
      supplier: { name: 'ZSE', ico: '36677281' },
      invoice: { number: '42', issue_date: '2026-06-20', document_type: 'credit_note' },
      handwritten: { date: null, number: '7' },
      totals: { gross: 150.5 },
      lines: [{ description: 'Elektrina', gross: 150.5 }],
      free_text: ['a', 'b'],
    });
    expect(values.supplier.name).toBe('ZSE');
    expect(values.invoice.document_type).toBe('credit_note');
    expect(values.handwritten).toEqual({ date: '', number: '7' });
    expect(values.totals.gross).toBe('150,50');
    expect(values.lines).toEqual([{ description: 'Elektrina', gross: '150,50' }]);
    expect(values.notes).toBe('a\nb');
    expect(valuesOf({}).supplier.name).toBe('');
  });
});
