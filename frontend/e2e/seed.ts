/**
 * What `riso seed` creates (riso/api/seed.py), for the specs. The global setup passes the
 * password through RISO_SEED_PASSWORD.
 */

export const SEED_PASSWORD = 'Ukážkové-heslo-2026';

export const USERS = {
  admin: { email: 'admin@riso.test', name: 'Alena Správcová' },
  staff: { email: 'peter.uctovnik@vzor.test', name: 'Peter Účtovník' },
  user: { email: 'jana.vzorova@boldog.test', name: 'Jana Vzorová' },
  viewer: { email: 'ivan.citatel@boldog.test', name: 'Ivan Čitateľ' },
} as const;

export const CUSTOMERS = {
  boldog: 'Obec Boldog',
  second: 'Obec Vzorová Lehota',
  unassigned: 'Obec Nezávislá',
} as const;

export const PROVIDER = 'Účtovníctvo Vzor, s.r.o.';
