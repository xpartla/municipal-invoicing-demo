import type { QueryClient } from '@tanstack/react-query';
import {
  createBrowserHistory,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
  type RouteComponent,
  type RouterHistory,
} from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { Shell } from '../components/Shell';
import { meQuery, useMe, type Me } from '../features/identity/api';
import {
  createsCustomers,
  onPlatform,
  seesProviderScreens,
  worksAcrossCustomers,
  type Permission,
} from '../features/identity/capabilities';
import { ConfirmEmailPage } from '../routes/auth/ConfirmEmailPage';
import { ForgotPasswordPage } from '../routes/auth/ForgotPasswordPage';
import { InvitationPage } from '../routes/auth/InvitationPage';
import { LoginPage } from '../routes/auth/LoginPage';
import { ResetPasswordPage } from '../routes/auth/ResetPasswordPage';
import { codelistsSearch } from '../features/codelists/kinds';
import { customerImportSearch, globalImportSearch } from '../features/exchange/search';
import { invoicesSearch } from '../features/invoices/search';
import { CodelistsPage } from '../routes/CodelistsPage';
import { ComingSoonPage } from '../routes/ComingSoonPage';
import { CustomerLayout } from '../routes/CustomerLayout';
import { ErrorPage } from '../routes/ErrorPage';
import { ExchangePage } from '../routes/ExchangePage';
import { ForbiddenPage } from '../routes/ForbiddenPage';
import { HomePage } from '../routes/HomePage';
import { ImportPage } from '../routes/ImportPage';
import { InvoicePage } from '../routes/InvoicePage';
import { InvoicesPage } from '../routes/InvoicesPage';
import { GlobalCodelistsPage } from '../routes/admin/GlobalCodelistsPage';
import { GlobalImportPage } from '../routes/admin/GlobalImportPage';
import { OutboxPage } from '../routes/admin/OutboxPage';
import { ProvidersPage } from '../routes/admin/ProvidersPage';
import { MessagesPage } from '../routes/MessagesPage';
import { NoAccessPage } from '../routes/NoAccessPage';
import { NewCustomerPage } from '../routes/NewCustomerPage';
import { NewInvoicePage } from '../routes/NewInvoicePage';
import { NotFoundPage } from '../routes/NotFoundPage';
import { ProfilePage } from '../routes/ProfilePage';
import { SystemPage } from '../routes/SystemPage';
import { UsersPage } from '../routes/UsersPage';

/**
 * Routes, code-based, mirroring plan §10.1. The pages before a login are public; everything
 * else sits under the `_app` layout, which needs a session (else /login?next=…) and renders
 * the shell. Customer pages are /c/$customerId/…: a customer the caller cannot open is a 404,
 * as the API answers. Screens a role may not see show the 403 page; the API refuses anyway.
 */

export interface RouterContext {
  queryClient: QueryClient;
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
  notFoundComponent: NotFoundPage,
  errorComponent: ErrorPage,
});

/** The caller, from the cache when it is there (a login or a logout set it). */
async function currentMe(context: RouterContext): Promise<Me | null> {
  return context.queryClient.query({ ...meQuery, staleTime: 'static' });
}

/** Sends a login to where it lands (plan §2 decision 53); returns when it has nowhere. */
function goToLanding(me: Me): void {
  if (worksAcrossCustomers(me)) throw redirect({ to: '/users' });
  const first = me.customers[0];
  if (first) throw redirect({ to: '/c/$customerId', params: { customerId: first.id } });
}

// Before a login --------------------------------------------------------------------------

interface LoginSearch {
  next?: string;
  notice?: 'password-set' | 'email-changed' | 'logged-out';
}

const NOTICES = new Set(['password-set', 'email-changed', 'logged-out']);

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  validateSearch: (search: Record<string, unknown>): LoginSearch => ({
    next: typeof search.next === 'string' ? search.next : undefined,
    notice:
      typeof search.notice === 'string' && NOTICES.has(search.notice)
        ? (search.notice as LoginSearch['notice'])
        : undefined,
  }),
  beforeLoad: async ({ context }) => {
    const me = await currentMe(context);
    if (me) goToLanding(me);
  },
  component: LoginPage,
});

const publicRoutes = [
  loginRoute,
  createRoute({ getParentRoute: () => rootRoute, path: '/invitation', component: InvitationPage }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/forgot-password',
    component: ForgotPasswordPage,
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/reset-password',
    component: ResetPasswordPage,
  }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/confirm-email',
    component: ConfirmEmailPage,
  }),
];

// After a login ---------------------------------------------------------------------------

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: '_app',
  beforeLoad: async ({ context, location }) => {
    const me = await currentMe(context);
    if (!me) throw redirect({ to: '/login', search: { next: location.href } });
  },
  component: Shell,
  notFoundComponent: NotFoundPage,
});

const indexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/',
  beforeLoad: async ({ context }) => {
    const me = await currentMe(context);
    if (me) goToLanding(me);
  },
  component: NoAccessPage,
});

const customerRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/c/$customerId',
  component: CustomerLayout,
});

type TitleKey =
  | 'invoices'
  | 'codelists'
  | 'exchange'
  | 'files'
  | 'system'
  | 'help'
  | 'profile'
  | 'providerOverview'
  | 'users'
  | 'platform'
  | 'providers'
  | 'globalCodelists'
  | 'audit'
  | 'jobs'
  | 'outbox'
  | 'evaluation';

/** A "Pripravujeme" page titled like its menu item. */
function soon(key: TitleKey) {
  return function Soon() {
    const { t } = useTranslation();
    return <ComingSoonPage title={t(`shell.nav.${key}`)} />;
  };
}

/** Renders `Page` when the caller may see it, the 403 page otherwise. */
function guarded(allowed: (me: Me) => boolean, Page: RouteComponent) {
  return function Guarded() {
    const { data: me } = useMe();
    return me && allowed(me) ? <Page /> : <ForbiddenPage />;
  };
}

const admin = (permission: Permission) => (me: Me) => onPlatform(me, permission);

const customerRoutes = [
  createRoute({ getParentRoute: () => customerRoute, path: '/', component: HomePage }),
  createRoute({
    getParentRoute: () => customerRoute,
    path: 'codelists',
    component: CodelistsPage,
    validateSearch: codelistsSearch,
  }),
  createRoute({ getParentRoute: () => customerRoute, path: 'system', component: SystemPage }),
  createRoute({ getParentRoute: () => customerRoute, path: 'exchange', component: ExchangePage }),
  createRoute({
    getParentRoute: () => customerRoute,
    path: 'exchange/import',
    component: ImportPage,
    validateSearch: customerImportSearch,
  }),
  createRoute({
    getParentRoute: () => customerRoute,
    path: 'invoices',
    component: InvoicesPage,
    validateSearch: invoicesSearch,
  }),
  createRoute({
    getParentRoute: () => customerRoute,
    path: 'invoices/new',
    component: NewInvoicePage,
  }),
  createRoute({
    getParentRoute: () => customerRoute,
    path: 'invoices/$invoiceId',
    component: InvoicePage,
  }),
  createRoute({ getParentRoute: () => customerRoute, path: 'files', component: soon('files') }),
];

function page<TPath extends string>(path: TPath, component: RouteComponent) {
  return createRoute({ getParentRoute: () => appRoute, path, component });
}

const appRoutes = [
  indexRoute,
  customerRoute.addChildren(customerRoutes),
  page('/messages', MessagesPage),
  page('/help', soon('help')),
  page('/profile', ProfilePage),
  page('/provider', guarded(seesProviderScreens, soon('providerOverview'))),
  page('/users', guarded(seesProviderScreens, UsersPage)),
  page('/users/new', guarded(createsCustomers, NewCustomerPage)),
  page('/admin', guarded(admin('providers.manage'), soon('platform'))),
  page('/admin/providers', guarded(admin('providers.manage'), ProvidersPage)),
  page('/admin/codelists', guarded(admin('codelists.global'), GlobalCodelistsPage)),
  createRoute({
    getParentRoute: () => appRoute,
    path: '/admin/codelists/import',
    component: guarded(admin('codelists.global'), GlobalImportPage),
    validateSearch: globalImportSearch,
  }),
  page('/admin/audit', guarded(admin('audit.read'), soon('audit'))),
  page('/admin/jobs', guarded(admin('jobs.manage'), soon('jobs'))),
  page('/admin/outbox', guarded(admin('outbox.read'), OutboxPage)),
  page('/admin/eval', guarded(admin('evaluation.read'), soon('evaluation'))),
];

const routeTree = rootRoute.addChildren([...publicRoutes, appRoute.addChildren(appRoutes)]);

export function createAppRouter(
  queryClient: QueryClient,
  history: RouterHistory = createBrowserHistory(),
) {
  return createRouter({
    routeTree,
    history,
    context: { queryClient },
    defaultPreload: 'intent',
    defaultNotFoundComponent: NotFoundPage,
  });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter;
  }
}
