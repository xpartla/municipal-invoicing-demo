import { ARTICLES, type ArticleId, type HelpGroup } from './topics';

/**
 * The articles' Markdown (`sk/<id>.md`), bundled as text. Each starts with its `# Title`
 * and a lead paragraph; the index shows both. Imported only by the lazily loaded help
 * screens and panel, so the text stays out of the main bundle.
 */

const FILES = import.meta.glob<string>('./sk/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
});

export interface Article {
  id: ArticleId;
  group: HelpGroup;
  title: string;
  /** The first paragraph after the title. */
  lead: string;
  /** The Markdown after the title line. */
  body: string;
}

export function parseArticle(id: ArticleId, group: HelpGroup, markdown: string): Article {
  const text = markdown.replace(/\r\n/g, '\n').trim();
  const match = /^# (.+)\n/.exec(text);
  if (!match?.[1]) throw new Error(`help article ${id} does not start with a "# " title`);
  const body = text.slice(match[0].length).trim();
  const lead = plainText(body.split(/\n\s*\n/)[0] ?? '');
  return { id, group, title: match[1].trim(), lead, body };
}

/** Markdown's inline marks removed: links keep their text, emphasis and code their content. */
export function plainText(markdown: string): string {
  return markdown
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/(\*\*|__|\*|_|`)(.+?)\1/g, '$2')
    .replace(/\s+/g, ' ')
    .trim();
}

function load(): ReadonlyMap<ArticleId, Article> {
  const articles = new Map<ArticleId, Article>();
  for (const { id, group } of ARTICLES) {
    const markdown = FILES[`./sk/${id}.md`];
    if (markdown === undefined) throw new Error(`help article ${id} has no file sk/${id}.md`);
    articles.set(id, parseArticle(id, group, markdown));
  }
  return articles;
}

const ALL = load();

export function getArticle(id: ArticleId): Article {
  const article = ALL.get(id);
  if (!article) throw new Error(`unknown help article ${id}`);
  return article;
}

export function allArticles(): readonly Article[] {
  return [...ALL.values()];
}

/** The files that are not in `ARTICLES` (a test keeps this empty). */
export function strayFiles(): string[] {
  const known = new Set(ARTICLES.map(({ id }) => `./sk/${id}.md`));
  return Object.keys(FILES).filter((path) => !known.has(path));
}
