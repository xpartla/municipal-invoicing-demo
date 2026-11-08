import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../test/render';

describe('the shell', () => {
  it('shows the navbar frame with Domov and the placeholder items', async () => {
    await renderApp('/');
    const nav = screen.getByRole('navigation', { name: 'Hlavné menu' });
    expect(within(nav).getByRole('link', { name: 'Domov' })).toBeInTheDocument();
    for (const item of ['Faktúry', 'Číselníky', 'Importy a exporty', 'Úložisko', 'Systém']) {
      expect(within(nav).getByText(item)).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: 'Nová faktúra' })).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Pôvodná ukážka' })).toHaveAttribute(
      'href',
      '/index.html',
    );
  });

  it('renders Domov at /', async () => {
    await renderApp('/');
    expect(screen.getByRole('heading', { level: 1, name: 'Domov' })).toBeInTheDocument();
  });

  it('renders the not-found page for an unknown route', async () => {
    await renderApp('/no/such/page');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Stránka sa nenašla' }),
    ).toBeInTheDocument();
  });

  it('switches between the light and the dark theme', async () => {
    const user = userEvent.setup();
    await renderApp('/');
    const toDark = screen.getByRole('button', { name: 'Prepnúť na tmavý režim' });
    await user.click(toDark);
    expect(document.documentElement).toHaveAttribute('data-mantine-color-scheme', 'dark');
    expect(window.localStorage.getItem('mantine-color-scheme-value')).toBe('dark');
    await user.click(screen.getByRole('button', { name: 'Prepnúť na svetlý režim' }));
    expect(document.documentElement).toHaveAttribute('data-mantine-color-scheme', 'light');
  });
});
