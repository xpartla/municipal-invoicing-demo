import {
  ActionIcon,
  Anchor,
  AppShell,
  Burger,
  Button,
  Divider,
  Group,
  NavLink,
  Stack,
  Text,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Link, Outlet, useRouterState } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { tokens } from '../app/theme';

/**
 * The application frame of plan §10.1: the left navbar (a drawer on narrow screens) and the
 * content. The menu items are placeholders until the milestones that build their screens;
 * P2-M1 makes the menu depend on the caller's role.
 */

type MenuKey = 'invoices' | 'codelists' | 'exchange' | 'files' | 'messages' | 'system';
const PLACEHOLDERS: MenuKey[] = [
  'invoices',
  'codelists',
  'exchange',
  'files',
  'messages',
  'system',
];

export function Shell() {
  const { t } = useTranslation();
  const [opened, { toggle, close }] = useDisclosure(false);
  const pathname = useRouterState({ select: (state) => state.location.pathname });

  return (
    <AppShell
      header={{ height: tokens.headerHeight, collapsed: false }}
      navbar={{ width: tokens.navbarWidth, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label={t('shell.toggleNavigation')}
            />
            <Anchor component={Link} to="/" fw={700} size="lg" underline="never" onClick={close}>
              {t('app.name')}
            </Anchor>
            <Text c="dimmed" size="sm" visibleFrom="sm">
              {t('app.tagline')}
            </Text>
          </Group>
          <ColorSchemeToggle />
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm" aria-label={t('shell.nav.label')}>
        <AppShell.Section>
          <Tooltip label={t('shell.newInvoiceSoon')} withArrow>
            {/* The wrapper keeps the tooltip working on the disabled button. */}
            <div>
              <Button fullWidth size="md" disabled>
                {t('shell.newInvoice')}
              </Button>
            </div>
          </Tooltip>
        </AppShell.Section>

        <AppShell.Section grow mt="md">
          <Stack gap={2}>
            <NavLink
              component={Link}
              to="/"
              label={t('shell.nav.home')}
              active={pathname === '/'}
              onClick={close}
            />
            {PLACEHOLDERS.map((key) => (
              <NavLink
                key={key}
                label={t(`shell.nav.${key}`)}
                description={t('shell.nav.soon')}
                disabled
              />
            ))}
          </Stack>
        </AppShell.Section>

        <AppShell.Section>
          <Divider mb="xs" />
          <NavLink component="a" href="/index.html" label={t('shell.nav.legacyDemo')} />
          <NavLink label={t('shell.nav.help')} disabled />
          <NavLink label={t('shell.nav.profile')} disabled />
          <NavLink label={t('shell.nav.logout')} disabled />
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

function ColorSchemeToggle() {
  const { t } = useTranslation();
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme('light', { getInitialValueInEffect: false });
  const next = computed === 'dark' ? 'light' : 'dark';
  const label = next === 'light' ? t('shell.theme.toLight') : t('shell.theme.toDark');
  return (
    <ActionIcon
      variant="default"
      size="lg"
      aria-label={label}
      title={label}
      onClick={() => {
        setColorScheme(next);
      }}
    >
      <span aria-hidden="true">{next === 'light' ? '☀' : '☾'}</span>
    </ActionIcon>
  );
}
