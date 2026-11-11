import '@mantine/core/styles.css';
import '@mantine/charts/styles.css';
import '@mantine/notifications/styles.css';
import '../i18n';

import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';

import type { AppRouter } from './router';
import { colorSchemeManager, cssVariablesResolver, theme } from './theme';

export function AppProviders({
  queryClient,
  env,
  children,
}: {
  queryClient: QueryClient;
  /** "test" turns off Mantine's transitions and portals, for jsdom. */
  env?: 'default' | 'test';
  children: React.ReactNode;
}) {
  return (
    <MantineProvider
      env={env}
      theme={theme}
      cssVariablesResolver={cssVariablesResolver}
      colorSchemeManager={colorSchemeManager}
      defaultColorScheme="auto"
    >
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MantineProvider>
  );
}

export function App({
  router,
  queryClient,
  env,
}: {
  router: AppRouter;
  queryClient: QueryClient;
  env?: 'default' | 'test';
}) {
  return (
    <AppProviders queryClient={queryClient} env={env}>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
