import {
  ActionIcon,
  Anchor,
  AppShell,
  Burger,
  Button,
  Divider,
  Group,
  NavLink,
  ScrollArea,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconChevronsLeft,
  IconChevronsRight,
  IconFilePlus,
  IconHelp,
  IconLogout,
  IconUser,
  type Icon,
} from '@tabler/icons-react';
import {
  Link,
  Navigate,
  Outlet,
  useParams,
  useRouter,
  useRouterState,
} from '@tanstack/react-router';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { sessionExpiredKey } from '../app/queryClient';
import { tokens } from '../app/theme';
import { HelpTopicContext } from '../help/context';
import type { ArticleId } from '../help/topics';
import { useLogout, useMe, type Me } from '../features/identity/api';
import {
  currentCustomerId,
  inCustomer,
  worksAcrossCustomers,
} from '../features/identity/capabilities';
import { ColorSchemeToggle } from './ColorSchemeToggle';
import { HelpButton } from './HelpButton';
import { InShellContext } from './inShell';
import { CustomerSwitcher } from './CustomerSwitcher';
import { ImpersonationBanner } from './ImpersonationBanner';
import { menuFor, type Section } from './menu';
import { ActionIconLink, ButtonLink } from './RouterLinks';

/**
 * The application frame of plan §10.1: the left navbar (240 px, collapsible to icons, a
 * drawer on narrow screens) with the customer switcher, the large Nová faktúra button, the
 * menu per role and, at the bottom, Pomocník, Profil and Odhlásiť; the impersonation banner
 * above the content.
 */

const COLLAPSED_KEY = 'riso-navbar-collapsed';
const COLLAPSED_WIDTH = 72;

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

function writeCollapsed(value: boolean): void {
  try {
    window.localStorage.setItem(COLLAPSED_KEY, value ? '1' : '0');
  } catch {
    // a browser without storage keeps the navbar open
  }
}

export function Shell() {
  const { data: me } = useMe();
  const client = useQueryClient();
  // The page the caller was on: the location still being resolved may be the login itself.
  const href = useRouterState({
    select: (state) => (state.resolvedLocation ?? state.location).href,
  });
  if (!me) {
    // The session ended under the caller: back to the login, which returns them here.
    if (client.getQueryData<boolean>(sessionExpiredKey) === true) {
      return <Navigate to="/login" search={{ notice: 'session-expired', next: href }} />;
    }
    return <Navigate to="/login" />;
  }
  return <ShellFor me={me} />;
}

function ShellFor({ me }: { me: Me }) {
  const { t } = useTranslation();
  const [opened, { toggle, close }] = useDisclosure(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const params: { customerId?: string } = useParams({ strict: false });
  const customerId = currentCustomerId(me, params.customerId);
  const showSwitcher = worksAcrossCustomers(me) || me.customers.length > 1;
  const [pageTopic, setPageTopic] = useState<ArticleId>();

  return (
    <InShellContext.Provider value>
      <HelpTopicContext.Provider value={setPageTopic}>
        <AppShell
          header={{ height: tokens.headerHeight }}
          navbar={{
            width: collapsed ? COLLAPSED_WIDTH : tokens.navbarWidth,
            breakpoint: 'sm',
            collapsed: { mobile: !opened },
          }}
          padding="md"
        >
          <AppShell.Header>
            <Group h="100%" px="md" justify="space-between" wrap="nowrap">
              <Group gap="sm" wrap="nowrap">
                <Burger
                  opened={opened}
                  onClick={toggle}
                  hiddenFrom="sm"
                  size="sm"
                  aria-label={t('shell.toggleNavigation')}
                />
                <Anchor
                  component={Link}
                  to="/"
                  fw={700}
                  size="lg"
                  underline="never"
                  onClick={close}
                >
                  {t('app.name')}
                </Anchor>
                <Text c="dimmed" size="sm" visibleFrom="md">
                  {t('app.tagline')}
                </Text>
              </Group>
              <Group gap="sm" wrap="nowrap">
                <Text size="sm" visibleFrom="sm" truncate maw={240}>
                  {me.user.name}
                </Text>
                <HelpButton pageTopic={pageTopic} />
                <ColorSchemeToggle />
              </Group>
            </Group>
          </AppShell.Header>

          <AppShell.Navbar p="sm" aria-label={t('shell.nav.label')}>
            {showSwitcher && !collapsed && (
              <AppShell.Section mb="sm">
                <CustomerSwitcher me={me} customerId={customerId} onChosen={close} />
              </AppShell.Section>
            )}
            <AppShell.Section>
              {customerId && inCustomer(me, customerId, 'invoices.process') ? (
                collapsed ? (
                  <Tooltip label={t('shell.newInvoice')} withArrow position="right">
                    <ActionIconLink
                      size="xl"
                      to="/c/$customerId/invoices/new"
                      params={{ customerId }}
                      aria-label={t('shell.newInvoice')}
                      onClick={close}
                    >
                      <IconFilePlus aria-hidden />
                    </ActionIconLink>
                  </Tooltip>
                ) : (
                  <ButtonLink
                    fullWidth
                    size="md"
                    to="/c/$customerId/invoices/new"
                    params={{ customerId }}
                    leftSection={<IconFilePlus size={20} aria-hidden />}
                    onClick={close}
                  >
                    {t('shell.newInvoice')}
                  </ButtonLink>
                )
              ) : (
                <Tooltip
                  label={
                    customerId ? t('shell.newInvoiceNotAllowed') : t('shell.newInvoiceNoCustomer')
                  }
                  withArrow
                  position="right"
                >
                  {/* The wrapper keeps the tooltip working on the disabled button. */}
                  <div>
                    {collapsed ? (
                      <ActionIcon size="xl" disabled aria-label={t('shell.newInvoice')}>
                        <IconFilePlus aria-hidden />
                      </ActionIcon>
                    ) : (
                      <Button
                        fullWidth
                        size="md"
                        disabled
                        leftSection={<IconFilePlus size={20} aria-hidden />}
                      >
                        {t('shell.newInvoice')}
                      </Button>
                    )}
                  </div>
                </Tooltip>
              )}
            </AppShell.Section>

            <AppShell.Section grow mt="md" component={ScrollArea}>
              <Menu me={me} customerId={customerId} collapsed={collapsed} onNavigate={close} />
            </AppShell.Section>

            <AppShell.Section>
              <Divider mb="xs" />
              <Stack gap={2}>
                <Item
                  to="/help"
                  icon={IconHelp}
                  label={t('shell.nav.help')}
                  collapsed={collapsed}
                  onNavigate={close}
                />
                <Item
                  to="/profile"
                  icon={IconUser}
                  label={t('shell.nav.profile')}
                  collapsed={collapsed}
                  onNavigate={close}
                />
                <LogoutItem collapsed={collapsed} />
                <Group justify={collapsed ? 'center' : 'flex-end'} visibleFrom="sm" mt={4}>
                  <ActionIcon
                    variant="subtle"
                    color="gray"
                    aria-label={collapsed ? t('shell.expand') : t('shell.collapse')}
                    title={collapsed ? t('shell.expand') : t('shell.collapse')}
                    onClick={() => {
                      setCollapsed(!collapsed);
                      writeCollapsed(!collapsed);
                    }}
                  >
                    {collapsed ? (
                      <IconChevronsRight aria-hidden />
                    ) : (
                      <IconChevronsLeft aria-hidden />
                    )}
                  </ActionIcon>
                </Group>
              </Stack>
            </AppShell.Section>
          </AppShell.Navbar>

          <AppShell.Main>
            <ImpersonationBanner me={me} />
            <Outlet />
          </AppShell.Main>
        </AppShell>
      </HelpTopicContext.Provider>
    </InShellContext.Provider>
  );
}

const SECTION_LABEL: Record<Exclude<Section, 'general'>, 'customer' | 'provider' | 'admin'> = {
  customer: 'customer',
  provider: 'provider',
  admin: 'admin',
};

function Menu({
  me,
  customerId,
  collapsed,
  onNavigate,
}: {
  me: Me;
  customerId: string | undefined;
  collapsed: boolean;
  onNavigate: () => void;
}) {
  const { t } = useTranslation();
  const items = menuFor(me, customerId);
  const sections = [...new Set(items.map((item) => item.section))];
  return (
    <Stack gap="xs">
      {sections.map((section) => (
        <Stack gap={2} key={section}>
          {section !== 'general' && !collapsed && (
            <Text size="xs" fw={600} c="dimmed" tt="uppercase" px="sm" pt={4}>
              {t(`shell.section.${SECTION_LABEL[section]}`)}
            </Text>
          )}
          {items
            .filter((item) => item.section === section)
            .map((item) => (
              <Item
                key={item.key}
                to={item.path(customerId ?? '')}
                icon={item.icon}
                label={t(`shell.nav.${item.key}`)}
                collapsed={collapsed}
                exact={item.key === 'home'}
                onNavigate={onNavigate}
              />
            ))}
        </Stack>
      ))}
    </Stack>
  );
}

function Item({
  to,
  icon: ItemIcon,
  label,
  collapsed,
  exact = false,
  onNavigate,
}: {
  to: string;
  icon: Icon;
  label: string;
  collapsed: boolean;
  exact?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const active = exact ? pathname === to : pathname === to || pathname.startsWith(`${to}/`);
  const link = (
    <NavLink
      component={Link}
      to={to}
      label={collapsed ? undefined : label}
      aria-label={collapsed ? label : undefined}
      leftSection={<ItemIcon size={20} aria-hidden />}
      active={active}
      // The router's own notion of active (aria-current) must agree: by default it counts
      // Domov (/c/:id) as active on every customer page.
      activeOptions={{ exact }}
      onClick={onNavigate}
    />
  );
  return collapsed ? (
    <Tooltip label={label} position="right" withArrow>
      {link}
    </Tooltip>
  ) : (
    link
  );
}

function LogoutItem({ collapsed }: { collapsed: boolean }) {
  const { t } = useTranslation();
  const router = useRouter();
  const logout = useLogout();
  const label = t('shell.nav.logout');
  return (
    <NavLink
      component="button"
      type="button"
      label={collapsed ? undefined : label}
      aria-label={collapsed ? label : undefined}
      leftSection={<IconLogout size={20} aria-hidden />}
      disabled={logout.isPending}
      onClick={() => {
        void logout.mutateAsync().finally(() => {
          router.history.push('/login?notice=logged-out');
        });
      }}
    />
  );
}
