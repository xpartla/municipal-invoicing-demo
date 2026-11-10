import { formatAmount, formatDate } from '../../lib/format';
import catalogue from '../../i18n/sk/engine.json';

/**
 * The engine's messages in Slovak (moved from the demo's `messages-sk.json`, P2-M4-T08). The
 * API speaks English, the integration contract; each message matches one pattern of the
 * catalogue, whose template takes the pattern's groups, converted by kind: `{1:amount}`,
 * `{2:concepts}` … `tests/test_engine_messages.py` checks that every message the dataset
 * produces has a pattern.
 */

interface Catalogue {
  messages: [string, string][];
  checks: Record<string, string>;
  roles: Record<string, string>;
  confidence: Record<string, string>;
  fields: Record<string, string>;
  concepts: Record<string, string>;
  functions: Record<string, string>;
}

const data = catalogue as unknown as Catalogue;
const compiled = data.messages.map(([pattern, text]) => [new RegExp(pattern), text] as const);

function percent(value: number): string {
  return `${String(Math.round(value * 100))} %`;
}

function functionName(code: string): string {
  const name = data.functions[code];
  return name ? `${code} (${name})` : code;
}

/** Where in the invoice a word was found, after the preposition "v". */
function pathName(path: string): string {
  let found = /^lines\[(\d+)\]\.\w+$/.exec(path);
  if (found) return `položke ${String(Number(found[1]) + 1)}`;
  found = /^free_text\[(\d+)\]$/.exec(path);
  if (found) return `poznámke ${String(Number(found[1]) + 1)}`;
  if (path === 'supplier.name') return 'názve dodávateľa';
  return path;
}

function fieldName(path: string): string {
  let found = /^lines\[(\d+)\]\.gross$/.exec(path);
  if (found) return `suma položky ${String(Number(found[1]) + 1)}`;
  found = /^lines\[(\d+)\]\.\w+$/.exec(path);
  if (found) return `položka ${String(Number(found[1]) + 1)}`;
  return data.fields[path] ?? path;
}

function concepts(value: string): string {
  return value
    .split(', ')
    .map((name) => data.concepts[name] ?? name)
    .join(', ');
}

function auReason(reason: string): string {
  if (reason === 'default') return 'predvolená';
  return reason
    .split('; ')
    .map((part) => {
      let found = /^concept (.+)$/.exec(part);
      if (found?.[1]) return `pojem ${concepts(found[1])}`;
      found = /^function (.+)$/.exec(part);
      if (found?.[1]) return `funkcia ${found[1].split(', ').map(functionName).join(', ')}`;
      found = /^term (.+)$/.exec(part);
      if (found?.[1]) return `slovo ${found[1]}`;
      return part;
    })
    .join('; ');
}

function convert(value: string, kind: string | undefined): string {
  switch (kind) {
    case 'amount':
      return formatAmount(Number(value));
    case 'date':
      return formatDate(value);
    case 'percent':
      return percent(Number(value));
    case 'role':
      return data.roles[value] ?? value;
    case 'confidence':
      return data.confidence[value] ?? value;
    case 'field':
      return fieldName(value);
    case 'path':
      return pathName(value);
    case 'concepts':
      return concepts(value);
    case 'function':
      return functionName(value);
    case 'functions':
      return value.split(', ').map(functionName).join(', ');
    case 'document':
      return value === 'an earlier invoice' ? 'skoršia faktúra' : value;
    case 'au':
      return auReason(value);
    default:
      return value;
  }
}

/** The engine's message in Slovak; a message without a pattern stays as it is. */
export function engineText(text: string | null | undefined): string {
  if (!text) return '';
  for (const [pattern, template] of compiled) {
    const found = pattern.exec(text);
    if (found) {
      return template.replace(/\{(\d+)(?::(\w+))?\}/g, (_, n: string, kind?: string) =>
        convert(found[Number(n)] ?? '', kind),
      );
    }
  }
  return text;
}

/** A passed check's Slovak name. */
export function checkName(name: string): string {
  return data.checks[name] ?? name;
}

export { percent as formatPercent };
