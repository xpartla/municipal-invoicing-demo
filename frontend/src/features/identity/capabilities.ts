import type { Me } from './api';

/**
 * What the caller may do, from `/api/me` (plan §5.2, §10.1). The screens hide what the
 * caller cannot do, but hidden is not secure: the API checks everything again.
 */

export type Permission = Me['platform'][number];

export function onPlatform(me: Me, permission: Permission): boolean {
  return me.platform.includes(permission);
}

export function inAnyProvider(me: Me, permission: Permission): boolean {
  return me.providers.some((p) => p.permissions.includes(permission));
}

export function inCustomer(me: Me, customerId: string, permission: Permission): boolean {
  return me.customers.some((c) => c.id === customerId && c.permissions.includes(permission));
}

export function canOpenCustomer(me: Me, customerId: string): boolean {
  return me.customers.some((c) => c.id === customerId);
}

/** Staff of a provider or a platform admin: they work across customers. */
export function worksAcrossCustomers(me: Me): boolean {
  return me.providers.length > 0 || me.platform.length > 0;
}

/** Prehľad klientov and Používatelia: staff (their provider) and admins (every provider). */
export function seesProviderScreens(me: Me): boolean {
  return inAnyProvider(me, 'provider.overview') || onPlatform(me, 'provider.overview');
}

/** Nový klient: staff (into their provider) and admins (plan §5.2). */
export function createsCustomers(me: Me): boolean {
  return inAnyProvider(me, 'customers.create') || onPlatform(me, 'customers.create');
}

/**
 * The customer the navbar's customer items point at: the one in the URL, else a customer
 * user's only customer. Staff and admins choose one first (plan §10.1).
 */
export function currentCustomerId(me: Me, fromUrl: string | undefined): string | undefined {
  if (fromUrl && canOpenCustomer(me, fromUrl)) return fromUrl;
  if (!worksAcrossCustomers(me) && me.customers.length === 1) return me.customers[0]?.id;
  return undefined;
}

/** Where a login lands (plan §2 decision 53). */
export function landingPath(me: Me): string | undefined {
  if (worksAcrossCustomers(me)) return '/users';
  const first = me.customers[0];
  return first ? `/c/${first.id}` : undefined;
}

/** A `next` parameter is followed only within the app. */
export function safeNext(next: unknown): string | undefined {
  return typeof next === 'string' && next.startsWith('/') && !next.startsWith('//')
    ? next
    : undefined;
}
