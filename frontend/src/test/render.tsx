import { createMemoryHistory } from '@tanstack/react-router';
import { render, screen } from '@testing-library/react';

import { App } from '../app/App';
import { createAppRouter } from '../app/router';

/** Renders the whole app at `path`, with a memory history, and waits for the page. */
export async function renderApp(path = '/') {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const result = render(<App router={router} />);
  await screen.findByRole('main');
  return { ...result, router };
}
