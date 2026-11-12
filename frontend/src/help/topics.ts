/**
 * The help centre's table of contents (plan §10.10, decision 68): which articles there are,
 * the role group each belongs to, and which article a screen's "?" opens. This module is
 * light on purpose: the shell imports it on every page, while the articles and the Markdown
 * renderer load only when help is opened (`articles.ts`).
 */

export const HELP_GROUPS = ['customer', 'staff', 'admin'] as const;
export type HelpGroup = (typeof HELP_GROUPS)[number];

/** The articles in the order the index lists them; the ID is the file `sk/<id>.md`. */
export const ARTICLES = [
  { id: 'zaciname', group: 'customer' },
  { id: 'ako-to-funguje', group: 'customer' },
  { id: 'skenovanie', group: 'customer' },
  { id: 'kontrola-udajov', group: 'customer' },
  { id: 'navrh', group: 'customer' },
  { id: 'opravy', group: 'customer' },
  { id: 'faktury', group: 'customer' },
  { id: 'export-do-topsetu', group: 'customer' },
  { id: 'ciselne-rady', group: 'customer' },
  { id: 'ciselniky-a-importy', group: 'customer' },
  { id: 'system', group: 'customer' },
  { id: 'prechod-na-novy-rok', group: 'customer' },
  { id: 'klienti', group: 'staff' },
  { id: 'globalne-ciselniky', group: 'admin' },
  { id: 'sprava-platformy', group: 'admin' },
] as const satisfies readonly { id: string; group: HelpGroup }[];

export type ArticleId = (typeof ARTICLES)[number]['id'];

const IDS = new Set<string>(ARTICLES.map((article) => article.id));

export function isArticleId(value: string): value is ArticleId {
  return IDS.has(value);
}

type Search = Record<string, unknown>;
type Topic = ArticleId | ((search: Search) => ArticleId);

/**
 * The article each signed-in screen's "?" opens, by the route's full path (no trailing
 * slash). A test walks the route tree and fails when a route has none.
 */
export const HELP_BY_ROUTE: Readonly<Record<string, Topic>> = {
  '/': 'zaciname',
  '/c/$customerId': 'zaciname',
  '/c/$customerId/invoices': 'faktury',
  '/c/$customerId/invoices/new': 'skenovanie',
  // The page names its tab's article itself (`useHelpTopic`): its default tab depends on the
  // invoice's state, which the path does not show.
  '/c/$customerId/invoices/$invoiceId': 'navrh',
  '/c/$customerId/codelists': 'ciselniky-a-importy',
  '/c/$customerId/exchange': 'ciselniky-a-importy',
  '/c/$customerId/exchange/import': 'ciselniky-a-importy',
  '/c/$customerId/files': 'zaciname',
  '/c/$customerId/system': (search) => (search.tab === 'series' ? 'ciselne-rady' : 'system'),
  '/messages': 'zaciname',
  '/help': 'zaciname',
  '/help/$articleId': 'zaciname',
  '/profile': 'zaciname',
  '/provider': 'klienti',
  '/users': 'klienti',
  '/users/new': 'klienti',
  '/admin': 'sprava-platformy',
  '/admin/providers': 'sprava-platformy',
  '/admin/codelists': 'globalne-ciselniky',
  '/admin/codelists/import': 'globalne-ciselniky',
  '/admin/audit': 'sprava-platformy',
  '/admin/jobs': 'sprava-platformy',
  '/admin/outbox': 'sprava-platformy',
  '/admin/eval': 'sprava-platformy',
  '/$': 'zaciname',
};

export function normalisePath(fullPath: string): string {
  return fullPath.length > 1 && fullPath.endsWith('/') ? fullPath.slice(0, -1) : fullPath;
}

/** The article for a screen; `undefined` for a path the table does not know. */
export function topicFor(fullPath: string, search: Search = {}): ArticleId | undefined {
  const topic = HELP_BY_ROUTE[normalisePath(fullPath)];
  return typeof topic === 'function' ? topic(search) : topic;
}
