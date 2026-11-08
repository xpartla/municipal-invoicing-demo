import {
  IconArrowsExchange,
  IconBriefcase,
  IconChartBar,
  IconFileInvoice,
  IconFolder,
  IconHistory,
  IconHome,
  IconLayoutDashboard,
  IconListCheck,
  IconListDetails,
  IconMail,
  IconMessage,
  IconServer,
  IconSettings,
  IconUsers,
  IconWorld,
  type Icon,
} from '@tabler/icons-react';

import type { Me } from '../features/identity/api';
import { onPlatform, seesProviderScreens } from '../features/identity/capabilities';

/**
 * The navbar of plan §10.1, per role. Customer items appear once a customer is chosen (a
 * customer user's only customer counts as chosen); provider items for staff and admins;
 * admin items for admins. Items whose screens come later open a "Pripravujeme" page
 * (plan §2 decision 53).
 */

export type MenuKey =
  | 'home'
  | 'invoices'
  | 'codelists'
  | 'exchange'
  | 'files'
  | 'system'
  | 'messages'
  | 'providerOverview'
  | 'users'
  | 'platform'
  | 'providers'
  | 'globalCodelists'
  | 'audit'
  | 'jobs'
  | 'outbox'
  | 'evaluation';

export type Section = 'customer' | 'general' | 'provider' | 'admin';

export interface MenuItem {
  key: MenuKey;
  section: Section;
  icon: Icon;
  /** The path; customer items get the customer's ID. */
  path: (customerId: string) => string;
  visible: (me: Me) => boolean;
}

const always = () => true;
const admin = (permission: Parameters<typeof onPlatform>[1]) => (me: Me) =>
  onPlatform(me, permission);

export const MENU: readonly MenuItem[] = [
  { key: 'home', section: 'customer', icon: IconHome, path: (c) => `/c/${c}`, visible: always },
  {
    key: 'invoices',
    section: 'customer',
    icon: IconFileInvoice,
    path: (c) => `/c/${c}/invoices`,
    visible: always,
  },
  {
    key: 'codelists',
    section: 'customer',
    icon: IconListDetails,
    path: (c) => `/c/${c}/codelists`,
    visible: always,
  },
  {
    key: 'exchange',
    section: 'customer',
    icon: IconArrowsExchange,
    path: (c) => `/c/${c}/exchange`,
    visible: always,
  },
  {
    key: 'files',
    section: 'customer',
    icon: IconFolder,
    path: (c) => `/c/${c}/files`,
    visible: always,
  },
  {
    key: 'system',
    section: 'customer',
    icon: IconSettings,
    path: (c) => `/c/${c}/system`,
    visible: always,
  },
  {
    key: 'messages',
    section: 'general',
    icon: IconMessage,
    path: () => '/messages',
    visible: always,
  },
  {
    key: 'providerOverview',
    section: 'provider',
    icon: IconLayoutDashboard,
    path: () => '/provider',
    visible: seesProviderScreens,
  },
  {
    key: 'users',
    section: 'provider',
    icon: IconUsers,
    path: () => '/users',
    visible: seesProviderScreens,
  },
  {
    key: 'platform',
    section: 'admin',
    icon: IconServer,
    path: () => '/admin',
    visible: admin('providers.manage'),
  },
  {
    key: 'providers',
    section: 'admin',
    icon: IconBriefcase,
    path: () => '/admin/providers',
    visible: admin('providers.manage'),
  },
  {
    key: 'globalCodelists',
    section: 'admin',
    icon: IconWorld,
    path: () => '/admin/codelists',
    visible: admin('codelists.global'),
  },
  {
    key: 'audit',
    section: 'admin',
    icon: IconHistory,
    path: () => '/admin/audit',
    visible: admin('audit.read'),
  },
  {
    key: 'jobs',
    section: 'admin',
    icon: IconListCheck,
    path: () => '/admin/jobs',
    visible: admin('jobs.manage'),
  },
  {
    key: 'outbox',
    section: 'admin',
    icon: IconMail,
    path: () => '/admin/outbox',
    visible: admin('outbox.read'),
  },
  {
    key: 'evaluation',
    section: 'admin',
    icon: IconChartBar,
    path: () => '/admin/eval',
    visible: admin('evaluation.read'),
  },
];

/** The items the caller sees, in order. Customer items need a chosen customer. */
export function menuFor(me: Me, customerId: string | undefined): MenuItem[] {
  return MENU.filter(
    (item) => item.visible(me) && (item.section !== 'customer' || customerId !== undefined),
  );
}
