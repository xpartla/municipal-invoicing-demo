import { describe, expect, it } from 'vitest';

import { allArticles, parseArticle, plainText, strayFiles } from './articles';
import { ARTICLES, isArticleId } from './topics';

/** The Markdown links of an article: `[text](target)`. */
function linkTargets(markdown: string): string[] {
  return [...markdown.matchAll(/\]\(([^)\s]+)\)/g)].map((match) => match[1] ?? '');
}

describe('the help articles', () => {
  it('has a file for every article and no file outside the list', () => {
    expect(allArticles().map((article) => article.id)).toEqual(ARTICLES.map(({ id }) => id));
    expect(strayFiles()).toEqual([]);
  });

  it('every article has a title, a lead and a body, and the titles differ', () => {
    for (const article of allArticles()) {
      expect(article.title, article.id).not.toBe('');
      expect(article.lead.length, article.id).toBeGreaterThan(40);
      expect(article.body.length, article.id).toBeGreaterThan(article.lead.length);
    }
    const titles = allArticles().map((article) => article.title);
    expect(new Set(titles).size).toBe(titles.length);
  });

  it('links only to articles that exist or to the web', () => {
    const broken = allArticles().flatMap((article) =>
      linkTargets(article.body)
        .filter((target) => !isArticleId(target) && !/^https?:/.test(target))
        .map((target) => `${article.id} → ${target}`),
    );
    expect(broken).toEqual([]);
  });

  it('every article but the index pages is linked from another one', () => {
    const linked = new Set(allArticles().flatMap((article) => linkTargets(article.body)));
    const unlinked = allArticles()
      .map((article) => article.id)
      .filter((id) => !linked.has(id) && id !== 'zaciname');
    expect(unlinked).toEqual([]);
  });

  it('writes no raw HTML, which the renderer would drop', () => {
    for (const article of allArticles()) {
      expect(/<[a-z][^>]*>/i.test(article.body), article.id).toBe(false);
    }
  });

  it('parses the title and the lead and refuses a file without a title', () => {
    const article = parseArticle(
      'zaciname',
      'customer',
      '# Názov\n\nPrvý **odsek** s [odkazom](navrh).\n\n## Ďalej\n\nText.',
    );
    expect(article.title).toBe('Názov');
    expect(article.lead).toBe('Prvý odsek s odkazom.');
    expect(article.body.startsWith('Prvý')).toBe(true);
    expect(() => parseArticle('zaciname', 'customer', 'Bez nadpisu')).toThrow(/title/);
  });

  it('turns inline Markdown into plain text', () => {
    expect(plainText('**Tučné**, *šikmé*, `kód` a [odkaz](x)')).toBe('Tučné, šikmé, kód a odkaz');
  });
});
