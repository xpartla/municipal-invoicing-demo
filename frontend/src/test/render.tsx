import { createMemoryHistory } from '@tanstack/react-router';
import { render, screen } from '@testing-library/react';

import { App } from '../app/App';
import { createQueryClient } from '../app/queryClient';
import { createAppRouter } from '../app/router';

/** Renders the whole app at `path`, with a memory history, and waits for the page. Stub the
 * API first with `mockApi`. */
export async function renderApp(path = '/') {
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false, staleTime: Infinity } });
  const router = createAppRouter(queryClient, createMemoryHistory({ initialEntries: [path] }));
  const result = render(<App router={router} queryClient={queryClient} env="test" />);
  await screen.findByRole('main');
  return { ...result, router, queryClient };
}
