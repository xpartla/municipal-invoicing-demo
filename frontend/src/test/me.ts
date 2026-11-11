import type { Me } from '../features/identity/api';

/** `/api/me` bodies per role, as the backend builds them (plan §5.2). */

const VIEWER = ['account.own', 'customer.read'] as const;
const USER = [
  ...VIEWER,
  'codelists.edit',
  'customer.edit_contact',
  'invoices.process',
  'templates.create_customer',
  'templates.use',
] as const;
const STAFF = [
  'account.own',
  'codelists.edit',
  'customer.assign_variable_number',
  'customer.edit_contact',
  'customer.edit_identity',
  'customer.read',
  'customers.create',
  'invoices.process',
  'logins.manage',
  'provider.overview',
  'templates.create_provider',
  'templates.use',
] as const;
const ADMIN = [
  ...STAFF,
  'audit.read',
  'codelists.global',
  'customer.data_export',
  'customers.delete',
  'evaluation.read',
  'jobs.manage',
  'outbox.read',
  'platform.overview',
  'providers.manage',
  'templates.create_customer',
  'templates.create_global',
  'users.administer',
  'users.delete',
  'users.impersonate',
] as const;

export const BOLDOG = { id: 'c-boldog', name: 'Obec Boldog', ico: '00305863', provider_id: 'p1' };
export const LEHOTA = {
  id: 'c-lehota',
  name: 'Obec Vzorová Lehota',
  ico: '99900017',
  provider_id: 'p1',
};
export const NEZAVISLA = {
  id: 'c-alone',
  name: 'Obec Nezávislá',
  ico: '99900025',
  provider_id: null,
};

type Role = 'viewer' | 'user' | 'staff' | 'admin';

interface Customer {
  id: string;
  name: string;
  ico: string;
  provider_id: string | null;
}

function person(id: string, name: string, email: string) {
  return {
    id,
    name,
    email,
    notification_email: null,
    status: 'active' as const,
    locked: false,
    memberships: [],
  };
}

const session = {
  id: 's1',
  created_at: '2026-06-11T08:00:00Z',
  last_seen_at: '2026-06-11T08:00:00Z',
  expires_at: '2026-06-11T16:00:00Z',
  ip: null,
  user_agent: null,
  current: true,
};

export function meAs(role: Role, overrides: Partial<Me> = {}): Me {
  const customerAccess = (perms: readonly string[], ...customers: Customer[]) =>
    customers.map((c) => ({ ...c, permissions: [...perms] })) as Me['customers'];
  const base: Record<Role, Me> = {
    viewer: {
      user: person('u-viewer', 'Ivan Čitateľ', 'ivan.citatel@boldog.test'),
      session,
      impersonation: null,
      platform: [],
      providers: [],
      customers: customerAccess(VIEWER, BOLDOG),
    },
    user: {
      user: person('u-user', 'Jana Vzorová', 'jana.vzorova@boldog.test'),
      session,
      impersonation: null,
      platform: [],
      providers: [],
      customers: customerAccess(USER, BOLDOG),
    },
    staff: {
      user: person('u-staff', 'Peter Účtovník', 'peter.uctovnik@vzor.test'),
      session,
      impersonation: null,
      platform: [],
      providers: [{ id: 'p1', name: 'Účtovníctvo Vzor, s.r.o.', permissions: [...STAFF] }],
      customers: customerAccess(STAFF, BOLDOG, LEHOTA),
    },
    admin: {
      user: person('u-admin', 'Alena Správcová', 'admin@riso.test'),
      session,
      impersonation: null,
      platform: [...ADMIN] as Me['platform'],
      providers: [],
      customers: customerAccess(ADMIN, BOLDOG, NEZAVISLA, LEHOTA),
    },
  };
  return { ...base[role], ...overrides };
}
