import { describe, expect, it } from 'vitest';

import type { ColumnMapping } from './api';
import {
  choiceOf,
  choiceValue,
  missingRequired,
  newTransform,
  rowsText,
  setField,
  splitErrors,
  textToValues,
  valuesToText,
  withChoice,
} from './mapping';

// The mapping editor's pure parts (P2-M3-T08).

const mapping: ColumnMapping = {
  import_type: 'accounts',
  fields: { su: { column: 'SU', constant: null, transforms: [{ op: 'trim' }] } },
  skip_empty_key: true,
  duplicates: null,
  facts: [],
};

describe('the mapping editor', () => {
  it('turns the select into a source and back, keeping the transforms', () => {
    const su = mapping.fields?.su;
    expect(choiceValue(choiceOf(su))).toBe('column:SU');
    expect(withChoice(su, 'column:AU')).toEqual({
      column: 'AU',
      constant: null,
      transforms: [{ op: 'trim' }],
    });
    expect(withChoice(su, 'constant')).toEqual({
      column: null,
      constant: '',
      transforms: [{ op: 'trim' }],
    });
    expect(choiceValue(choiceOf(undefined))).toBe('none');
    expect(choiceValue(choiceOf({ column: null, constant: '41', transforms: [] }))).toBe(
      'constant',
    );
  });

  it('drops a field left without a source and names the required ones missing', () => {
    const cleared = setField(mapping, 'su', { column: null, constant: null, transforms: [] });
    expect(cleared.fields).toEqual({});
    const fields = [
      { name: 'su', required: true, derived: false },
      { name: 'au', required: true, derived: false },
      { name: 'code', required: true, derived: true },
      { name: 'description', required: false, derived: false },
    ];
    expect(missingRequired(mapping, fields)).toEqual(['au']);
    expect(missingRequired(cleared, fields)).toEqual(['su', 'au']);
  });

  it('writes the map transform as lines and reads them back', () => {
    const values = { Aktívny: 'active', 'P ': 'passive' };
    expect(textToValues(valuesToText(values))).toEqual({ Aktívny: 'active', P: 'passive' });
    expect(textToValues('bez rovnítka\n = x\nA=a')).toEqual({ A: 'a' });
  });

  it('starts each transform with the backend defaults', () => {
    expect(newTransform('zero_pad')).toEqual({ op: 'zero_pad', width: 3 });
    expect(newTransform('split')).toMatchObject({ op: 'split', index: 0, count: null });
    expect(newTransform('map')).toEqual({ op: 'map', values: {}, otherwise: 'keep' });
  });

  it('shortens long row lists and splits hard from confirmable errors', () => {
    expect(rowsText([3, 5])).toBe('3, 5');
    expect(rowsText([1, 2, 3, 4], 2)).toBe('1, 2 … (+2)');
    expect(rowsText([])).toBe('—');
    const issue = (confirmable: boolean) => ({
      severity: 'error' as const,
      code: 'x',
      message: 'x',
      rows: [],
      field: null,
      key: null,
      value: null,
      confirmable,
    });
    const { hard, confirmable } = splitErrors([issue(false), issue(true), issue(true)]);
    expect([hard.length, confirmable.length]).toEqual([1, 2]);
  });
});
