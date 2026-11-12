import { createMemoryHistory } from '@tanstack/react-router';
import { describe, expect, it } from 'vitest';

import { createQueryClient } from '../app/queryClient';
import { createAppRouter } from '../app/router';
import { ARTICLES, HELP_BY_ROUTE, isArticleId, normalisePath, topicFor } from './topics';

interface RouteLike {
  id: string;
  fullPath: string;
  children?: unknown;
}

/** The signed-in screens: the routes under the `_app` layout that have no child routes. */
function signedInScreens(): string[] {
  const router = createAppRouter(createQueryClient(), createMemoryHistory());
  const routes = Object.values(router.routesById) as RouteLike[];
  return routes
    .filter((route) => route.id.startsWith('/_app/'))
    .filter((route) => !route.children || Object.keys(route.children).length === 0)
    .map((route) => normalisePath(route.fullPath))
    .sort();
}

describe('the contextual help', () => {
  it('every signed-in route has a "?" target', () => {
    const screens = signedInScreens();
    expect(screens.length).toBeGreaterThan(20);
    const missing = screens.filter((path) => topicFor(path) === undefined);
    expect(missing).toEqual([]);
  });

  it('names no route that does not exist', () => {
    const screens = new Set(signedInScreens());
    expect(Object.keys(HELP_BY_ROUTE).filter((path) => !screens.has(path))).toEqual([]);
  });

  it('every target is an article', () => {
    for (const path of Object.keys(HELP_BY_ROUTE)) {
      for (const tab of [undefined, 'series', 'check', 'parameters']) {
        const topic = topicFor(path, { tab });
        expect(topic && isArticleId(topic), `${path} ${tab ?? ''}`).toBe(true);
      }
    }
  });

  it('Systém opens the number series article on its number series tab', () => {
    expect(topicFor('/c/$customerId/system', { tab: 'series' })).toBe('ciselne-rady');
    expect(topicFor('/c/$customerId/system', {})).toBe('system');
    expect(topicFor('/c/$customerId/')).toBe('zaciname');
  });

  it('lists every article once', () => {
    const ids = ARTICLES.map((article) => article.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
