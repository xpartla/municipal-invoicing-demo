import type { QueryClient } from '@tanstack/react-query';
import {
  createBrowserHistory,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  lazyRouteComponent,
  Outlet,
  redirect,
  type RouteComponent,
  type RouterHistory,
} from '@tanstack/react-router';

import { Shell } from '../components/Shell';
import { sessionExpiredKey } from './queryClient';
import { meQuery, useMe, type Me } from '../features/identity/api';
import {
  createsCustomers,
  onPlatform,
  seesProviderScreens,
  landingPath,
  type Permission,
} from '../features/identity/capabilities';
import { ConfirmEmailPage } from '../routes/auth/ConfirmEmailPage';
import { ForgotPasswordPage } from '../routes/auth/ForgotPasswordPage';
import { InvitationPage } from '../routes/auth/InvitationPage';
import { LoginPage } from '../routes/auth/LoginPage';
import { ResetPasswordPage } from '../routes/auth/ResetPasswordPage';
import { codelistsSearch } from '../features/codelists/kinds';
import { customerImportSearch, globalImportSearch } from '../features/exchange/search';
import { invoicePageSearch, invoicesSearch } from '../features/invoices/search';
import { filesSearch } from '../features/reporting/api';
import { auditSearch } from '../features/admin/audit';
import { jobsSearch } from '../features/admin/jobs';
import { homeSearch } from '../features/reporting/dashboard';
import { overviewSearch, platformSearch } from '../features/reporting/overview';
import { systemSearch } from '../features/system/search';
import { CodelistsPage } from '../routes/CodelistsPage';
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
import { AuditPage } from '../routes/admin/AuditPage';
import { EvalPage } from '../routes/admin/EvalPage';
import { JobsPage } from '../routes/admin/JobsPage';
import { PlatformPage } from '../routes/admin/PlatformPage';
import { ProvidersPage } from '../routes/admin/ProvidersPage';
import { MessagesPage } from '../routes/MessagesPage';
import { NoAccessPage } from '../routes/NoAccessPage';
import { NewCustomerPage } from '../routes/NewCustomerPage';
import { FilesPage } from '../routes/FilesPage';
import { NewInvoicePage } from '../routes/NewInvoicePage';
import { NotFoundPage } from '../routes/NotFoundPage';
import { ProfilePage } from '../routes/ProfilePage';
import { ProviderOverviewPage } from '../routes/ProviderOverviewPage';
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

/** Sends a login to where it lands (plan §2 decision 67); returns when it has nowhere. */
function goToLanding(me: Me): void {
  const path = landingPath(me);
  if (path === '/admin') throw redirect({ to: '/admin' });
  if (path === '/provider') throw redirect({ to: '/provider' });
  if (path === '/users') throw redirect({ to: '/users' });
  const first = me.customers[0];
  if (first) throw redirect({ to: '/c/$customerId', params: { customerId: first.id } });
}

// Before a login --------------------------------------------------------------------------

interface LoginSearch {
  next?: string;
  notice?: 'password-set' | 'email-changed' | 'logged-out' | 'session-expired';
}

const NOTICES = new Set(['password-set', 'email-changed', 'logged-out', 'session-expired']);

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
    if (!me) {
      const ended = context.queryClient.getQueryData<boolean>(sessionExpiredKey) === true;
      throw redirect({
        to: '/login',
        search: { next: location.href, notice: ended ? 'session-expired' : undefined },
      });
    }
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

/** Renders `Page` when the caller may see it, the 403 page otherwise. */
function guarded(allowed: (me: Me) => boolean, Page: RouteComponent) {
  return function Guarded() {
    const { data: me } = useMe();
    return me && allowed(me) ? <Page /> : <ForbiddenPage />;
  };
}

const admin = (permission: Permission) => (me: Me) => onPlatform(me, permission);

const customerRoutes = [
  createRoute({
    getParentRoute: () => customerRoute,
    path: '/',
    component: HomePage,
    validateSearch: homeSearch,
  }),
  createRoute({
    getParentRoute: () => customerRoute,
    path: 'codelists',
    component: CodelistsPage,
    validateSearch: codelistsSearch,
  }),
  createRoute({
    getParentRoute: () => customerRoute,
    path: 'system',
    component: SystemPage,
    validateSearch: systemSearch,
  }),
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
    validateSearch: invoicePageSearch,
  }),
  createRoute({
    getParentRoute: () => customerRoute,
    path: 'files',
    component: FilesPage,
    validateSearch: filesSearch,
  }),
];

function page<TPath extends string>(path: TPath, component: RouteComponent) {
  return createRoute({ getParentRoute: () => appRoute, path, component });
}

const appRoutes = [
  indexRoute,
  customerRoute.addChildren(customerRoutes),
  page('/messages', MessagesPage),
  page(
    '/help',
    lazyRouteComponent(() => import('../routes/HelpPage'), 'HelpPage'),
  ),
  page(
    '/help/$articleId',
    lazyRouteComponent(() => import('../routes/HelpArticlePage'), 'HelpArticlePage'),
  ),
  page('/profile', ProfilePage),
  createRoute({
    getParentRoute: () => appRoute,
    path: '/provider',
    component: guarded(seesProviderScreens, ProviderOverviewPage),
    validateSearch: overviewSearch,
  }),
  page('/users', guarded(seesProviderScreens, UsersPage)),
  page('/users/new', guarded(createsCustomers, NewCustomerPage)),
  createRoute({
    getParentRoute: () => appRoute,
    path: '/admin',
    component: guarded(admin('platform.overview'), PlatformPage),
    validateSearch: platformSearch,
  }),
  page('/admin/providers', guarded(admin('providers.manage'), ProvidersPage)),
  page('/admin/codelists', guarded(admin('codelists.global'), GlobalCodelistsPage)),
  createRoute({
    getParentRoute: () => appRoute,
    path: '/admin/codelists/import',
    component: guarded(admin('codelists.global'), GlobalImportPage),
    validateSearch: globalImportSearch,
  }),
  createRoute({
    getParentRoute: () => appRoute,
    path: '/admin/audit',
    component: guarded(admin('audit.read'), AuditPage),
    validateSearch: auditSearch,
  }),
  createRoute({
    getParentRoute: () => appRoute,
    path: '/admin/jobs',
    component: guarded(admin('jobs.manage'), JobsPage),
    validateSearch: jobsSearch,
  }),
  page('/admin/outbox', guarded(admin('outbox.read'), OutboxPage)),
  page('/admin/eval', guarded(admin('evaluation.read'), EvalPage)),
  // Any other address, inside the shell (after the login), rather than a bare page.
  page('$', NotFoundPage),
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
    // A screen's crash shows in its place, inside the shell; the root's catches the rest.
    defaultErrorComponent: ErrorPage,
  });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter;
  }
}
