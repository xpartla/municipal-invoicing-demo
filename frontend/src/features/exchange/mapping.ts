import type { ColumnMapping, FieldSource, ImportType, Issue } from './api';

/** The import types per owner, in the wizard's order (plan §9.1). */
export const CUSTOMER_TYPES: readonly ImportType[] = [
  'accounts',
  'budget_expense',
  'budget_income',
  'document_series',
  'transfers',
  'cost_centres',
  'past_bookings',
];
export const GLOBAL_TYPES: readonly ImportType[] = [
  'ek',
  'cofog',
  'funding_sources',
  'framework_accounts',
];

export type Transform = NonNullable<FieldSource['transforms']>[number];
export type TransformOp = Transform['op'];
export const TRANSFORM_OPS: readonly TransformOp[] = [
  'trim',
  'zero_pad',
  'split',
  'decimal',
  'date',
  'map',
];

/** A new transform of the kind, with the backend's defaults. */
export function newTransform(op: TransformOp): Transform {
  switch (op) {
    case 'trim':
      return { op };
    case 'zero_pad':
      return { op, width: 3 };
    case 'split':
      return { op, separator: '\\s+', index: 0, count: null };
    case 'decimal':
      return { op, separator: 'auto' };
    case 'date':
      return { op, formats: ['%d.%m.%Y', '%Y-%m-%d', '%d/%m/%Y', '%d.%m.%y'] };
    case 'map':
      return { op, values: {}, otherwise: 'keep' };
  }
}

/** Where a field's value comes from, as the editor's select shows it. */
export type SourceChoice =
  { kind: 'none' } | { kind: 'column'; column: string } | { kind: 'constant' };

export function choiceOf(source: FieldSource | undefined): SourceChoice {
  if (source?.column != null) return { kind: 'column', column: source.column };
  if (source?.constant != null) return { kind: 'constant' };
  return { kind: 'none' };
}

/** The select's value for a choice: `column:<key>`, `constant` or `none`. */
export function choiceValue(choice: SourceChoice): string {
  return choice.kind === 'column' ? `column:${choice.column}` : choice.kind;
}

/** The field's source after choosing `value` in the select; its transforms are kept. */
export function withChoice(source: FieldSource | undefined, value: string): FieldSource {
  const transforms = source?.transforms ?? [];
  if (value.startsWith('column:')) {
    return { column: value.slice('column:'.length), constant: null, transforms };
  }
  if (value === 'constant') return { column: null, constant: source?.constant ?? '', transforms };
  return { column: null, constant: null, transforms };
}

/** The mapping with one field's source replaced; an empty source is left out. */
export function setField(mapping: ColumnMapping, name: string, source: FieldSource): ColumnMapping {
  const empty = source.column == null && source.constant == null && source.transforms.length === 0;
  const fields = Object.fromEntries(
    Object.entries(mapping.fields ?? {}).filter(([key]) => key !== name),
  );
  return { ...mapping, fields: empty ? fields : { ...fields, [name]: source } };
}

/** The required fields the mapping leaves without a source (a derived field needs none). */
export function missingRequired(
  mapping: ColumnMapping,
  fields: readonly { name: string; required: boolean; derived: boolean }[],
): string[] {
  return fields
    .filter((f) => f.required && !f.derived)
    .filter((f) => {
      const source = mapping.fields?.[f.name];
      return source?.column == null && source?.constant == null;
    })
    .map((f) => f.name);
}

/** `A = active` per line, the map transform's table as text and back. */
export function valuesToText(values: Record<string, string>): string {
  return Object.entries(values)
    .map(([from, to]) => `${from} = ${to}`)
    .join('\n');
}

export function textToValues(text: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const line of text.split('\n')) {
    const at = line.indexOf('=');
    if (at < 0) continue;
    const from = line.slice(0, at).trim();
    if (from) values[from] = line.slice(at + 1).trim();
  }
  return values;
}

/** The rows an issue names, shortened: `3, 5, 8 … (+12)`. */
export function rowsText(rows: readonly number[] | undefined, shown = 8): string {
  if (!rows || rows.length === 0) return '—';
  const head = rows.slice(0, shown).join(', ');
  return rows.length > shown ? `${head} … (+${String(rows.length - shown)})` : head;
}

/** A hard error refuses applying; a confirmable one (against the global lists) needs the
 * confirmation (plan §2 decision 58). */
export function splitErrors(errors: readonly Issue[] | undefined) {
  const all = errors ?? [];
  return { hard: all.filter((e) => !e.confirmable), confirmable: all.filter((e) => e.confirmable) };
}
