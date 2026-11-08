import {
  createBrowserHistory,
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from '@tanstack/react-router';

import { Shell } from '../components/Shell';
import { HomePage } from '../routes/HomePage';
import { NotFoundPage } from '../routes/NotFoundPage';

/**
 * Routes, code-based, mirroring plan §10.1. Customer pages arrive under /c/$customerId in
 * P2-M1.
 */
const rootRoute = createRootRoute({ component: Shell, notFoundComponent: NotFoundPage });

const homeRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: HomePage });

const routeTree = rootRoute.addChildren([homeRoute]);

export function createAppRouter(history: RouterHistory = createBrowserHistory()) {
  return createRouter({ routeTree, history, defaultPreload: 'intent' });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter;
  }
}
