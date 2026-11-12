import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { mockApi } from '../test/api';
import { BOLDOG, meAs } from '../test/me';
import { renderApp } from '../test/render';

// Pomocník (P2-M8-T01, plan §10.10, decision 68): the articles grouped by role, an article as
// a page, and the "?" in the header opening the screen's article in a side panel.

const GROUPS = ['Spracovanie faktúr', 'Pre servisné účty', 'Pre administrátorov'];

async function groupsShownTo(role: 'user' | 'staff' | 'admin') {
  mockApi({ 'GET /api/me': { body: meAs(role) } });
  await renderApp('/help');
  await screen.findByRole('heading', { level: 1, name: 'Pomocník' });
  return screen
    .getAllByRole('heading', { level: 2 })
    .map((heading) => heading.textContent)
    .filter((name) => GROUPS.includes(name));
}

describe('Pomocník', () => {
  it('shows a customer user the customer articles', async () => {
    expect(await groupsShownTo('user')).toEqual(['Spracovanie faktúr']);
    const group = screen.getByRole('region', { name: 'Spracovanie faktúr' });
    expect(within(group).getByRole('link', { name: 'Ako to funguje' })).toHaveAttribute(
      'href',
      '/help/ako-to-funguje',
    );
    expect(within(group).getAllByRole('link')).toHaveLength(12);
  });

  it('adds the staff articles for staff and every group for an admin', async () => {
    expect(await groupsShownTo('staff')).toEqual(GROUPS.slice(0, 2));
  });

  it('shows an admin every group', async () => {
    expect(await groupsShownTo('admin')).toEqual(GROUPS);
  });

  it('opens an article as a page, its links leading to other articles', async () => {
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    const { router } = await renderApp('/help/ako-to-funguje');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Ako to funguje' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: '5. Čo program nerobí' })).toBeVisible();
    const [link] = screen.getAllByRole('link', { name: 'Kontrola údajov' });
    if (!link) throw new Error('no link to Kontrola údajov');
    await userEvent.click(link);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/help/kontrola-udajov');
    });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Kontrola údajov' }),
    ).toBeInTheDocument();
  });

  it('says so for an article that does not exist', async () => {
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    await renderApp('/help/nic-take');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Návod sa nenašiel' }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole('main')).getByRole('link', { name: 'Pomocník' }),
    ).toHaveAttribute('href', '/help');
  });
});

describe('the "?" of a screen', () => {
  it("opens the screen's article in a side panel, and other articles inside it", async () => {
    mockApi({ 'GET /api/me': { body: meAs('user') } });
    const { router } = await renderApp(`/c/${BOLDOG.id}/system?tab=series`);
    await userEvent.click(screen.getByRole('button', { name: 'Pomocník k tejto obrazovke' }));
    const panel = await screen.findByRole('dialog', { name: 'Pomocník' });
    expect(
      await within(panel).findByRole('heading', { level: 3, name: 'Číselné rady' }),
    ).toBeVisible();
    await userEvent.click(within(panel).getByRole('link', { name: 'Prechod na nový rok' }));
    expect(
      await within(panel).findByRole('heading', { level: 3, name: 'Prechod na nový rok' }),
    ).toBeVisible();
    expect(router.state.location.pathname).toBe(`/c/${BOLDOG.id}/system`);

    await userEvent.click(within(panel).getByRole('link', { name: 'Otvoriť ako stránku' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/help/prechod-na-novy-rok');
    });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Prechod na nový rok' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Pomocník' })).not.toBeInTheDocument();
    });
  });

  it("opens an admin screen's article for an admin", async () => {
    mockApi({
      'GET /api/me': { body: meAs('admin') },
      'GET /api/admin/outbox': { body: { items: [], total: 0 } },
    });
    await renderApp('/admin/outbox');
    await userEvent.click(screen.getByRole('button', { name: 'Pomocník k tejto obrazovke' }));
    const panel = await screen.findByRole('dialog', { name: 'Pomocník' });
    expect(
      await within(panel).findByRole('heading', { level: 3, name: 'Správa platformy' }),
    ).toBeVisible();
  });
});
