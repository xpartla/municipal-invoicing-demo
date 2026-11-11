/** Systém's tab in the URL, so Domov can link to the number series and the health report. */

export const SYSTEM_TABS = ['parameters', 'conventions', 'series', 'health'] as const;
export type SystemTab = (typeof SYSTEM_TABS)[number];

export interface SystemSearch {
  tab?: SystemTab;
}

export function systemSearch(raw: Record<string, unknown>): SystemSearch {
  return { tab: SYSTEM_TABS.find((tab) => tab === raw.tab) };
}
