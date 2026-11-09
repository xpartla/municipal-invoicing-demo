/**
 * The conventions document (riso.knowledge.Conventions) as the editor holds it. The API
 * sends it as JSON; `normalise` fills what an older or partial document leaves out.
 */

export interface Rule {
  au: string;
  concepts: string[];
  function: string[];
  ek: string[];
  zdroj: string[];
  terms: string[];
  note: string | null;
}

export interface AccountRules {
  default: string;
  rules: Rule[];
}

export interface Canteen {
  concepts: string[];
  function: string;
  zdroj: string;
  ek: string;
  analytika: string;
  alternatives: string[];
  md: string;
}

export interface Concept {
  terms: string[];
  ek: string[];
  weight: number;
  text: string | null;
}

export type Side = 'debit' | 'credit';

export interface ConventionsDocument {
  au_rules: Record<Side, Record<string, AccountRules>>;
  canteen: Canteen | null;
  concepts: Record<string, Concept>;
  transfers: { never: string[] };
}

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];

const text = (value: unknown, fallback = ''): string =>
  typeof value === 'string' ? value : fallback;

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function emptyRule(): Rule {
  return { au: '', concepts: [], function: [], ek: [], zdroj: [], terms: [], note: null };
}

function rule(value: unknown): Rule {
  const r = record(value);
  return {
    au: text(r.au),
    concepts: strings(r.concepts),
    function: strings(r.function),
    ek: strings(r.ek),
    zdroj: strings(r.zdroj),
    terms: strings(r.terms),
    note: typeof r.note === 'string' ? r.note : null,
  };
}

function side(value: unknown): Record<string, AccountRules> {
  return Object.fromEntries(
    Object.entries(record(value)).map(([su, rules]) => {
      const r = record(rules);
      return [
        su,
        {
          default: text(r.default, '000'),
          rules: (Array.isArray(r.rules) ? r.rules : []).map(rule),
        },
      ];
    }),
  );
}

export function normalise(raw: Record<string, unknown>): ConventionsDocument {
  const au = record(raw.au_rules);
  const canteen = raw.canteen === null || raw.canteen === undefined ? null : record(raw.canteen);
  return {
    au_rules: { debit: side(au.debit), credit: side(au.credit) },
    canteen: canteen && {
      concepts: strings(canteen.concepts),
      function: text(canteen.function),
      zdroj: text(canteen.zdroj),
      ek: text(canteen.ek),
      analytika: text(canteen.analytika),
      alternatives: strings(canteen.alternatives),
      md: text(canteen.md),
    },
    concepts: Object.fromEntries(
      Object.entries(record(raw.concepts)).map(([name, value]) => {
        const c = record(value);
        return [
          name,
          {
            terms: strings(c.terms),
            ek: strings(c.ek),
            weight: typeof c.weight === 'number' ? c.weight : 1,
            text: typeof c.text === 'string' ? c.text : null,
          },
        ];
      }),
    ),
    transfers: { never: strings(record(raw.transfers).never) },
  };
}

/** A rule's conditions in one line, for the table. */
export function conditions(
  rule: Rule,
  labels: Record<'concepts' | 'function' | 'ek' | 'zdroj' | 'terms', string>,
): string {
  return (['concepts', 'function', 'ek', 'zdroj', 'terms'] as const)
    .filter((name) => rule[name].length > 0)
    .map((name) => `${labels[name]}: ${rule[name].join(', ')}`)
    .join('; ');
}
