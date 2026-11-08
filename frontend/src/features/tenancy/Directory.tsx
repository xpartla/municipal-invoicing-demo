import {
  Anchor,
  Badge,
  Button,
  Group,
  Loader,
  Menu,
  Paper,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { IconDots, IconExternalLink, IconUserPlus } from '@tabler/icons-react';
import { Link } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import { useNotify } from '../../lib/notify';
import { useLoginAction, type LoginAction, type Me } from '../identity/api';
import { inCustomer, onPlatform } from '../identity/capabilities';
import { ImpersonateDialog } from '../identity/ImpersonateDialog';
import { useDirectory, type Customer, type CustomerWithLogins, type Login } from './api';
import { InviteLoginDialog, VariableNumberDialog } from './LoginDialogs';

/**
 * Používatelia, the customers with their logins nested (plan §10.8): invite a login,
 * deactivate and reactivate it, send a reset link, assign the variable number, open the
 * customer. Admins also impersonate a login.
 */
export function Directory({ me, scope }: { me: Me; scope: { providerId: string } | 'all' }) {
  const { t } = useTranslation();
  const directory = useDirectory(scope);
  const [inviteFor, setInviteFor] = useState<Customer | null>(null);
  const [vsFor, setVsFor] = useState<Customer | null>(null);
  const [impersonate, setImpersonate] = useState<{ id: string; name: string } | null>(null);

  if (directory.isPending) return <Loader aria-label={t('common.loading')} />;
  if (directory.isError) return <Text>{t('common.error')}</Text>;
  if (directory.data.length === 0) return <Text>{t('users.noCustomers')}</Text>;
  return (
    <Stack gap="md">
      {directory.data.map((entry) => (
        <CustomerCard
          key={entry.customer.id}
          me={me}
          entry={entry}
          onInvite={setInviteFor}
          onVariableNumber={setVsFor}
          onImpersonate={setImpersonate}
        />
      ))}
      <InviteLoginDialog
        customer={inviteFor}
        onClose={() => {
          setInviteFor(null);
        }}
      />
      <VariableNumberDialog
        customer={vsFor}
        onClose={() => {
          setVsFor(null);
        }}
      />
      <ImpersonateDialog
        user={impersonate}
        onClose={() => {
          setImpersonate(null);
        }}
      />
    </Stack>
  );
}

function CustomerCard({
  me,
  entry,
  onInvite,
  onVariableNumber,
  onImpersonate,
}: {
  me: Me;
  entry: CustomerWithLogins;
  onInvite: (customer: Customer) => void;
  onVariableNumber: (customer: Customer) => void;
  onImpersonate: (user: { id: string; name: string }) => void;
}) {
  const { t } = useTranslation();
  const { customer, logins } = entry;
  const manages = inCustomer(me, customer.id, 'logins.manage');
  const assignsVs = inCustomer(me, customer.id, 'customer.assign_variable_number');
  const headingId = `customer-${customer.id}`;
  return (
    <Paper withBorder p="md" radius="md" component="section" aria-labelledby={headingId}>
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start" gap="sm">
          <Stack gap={2}>
            <Title order={2} size="h4" id={headingId}>
              {customer.name}
            </Title>
            <Text size="sm" c="dimmed">
              {t('profile.customer.ico')} {customer.ico}
              {customer.variable_number
                ? ` · ${t('users.variableNumber')} ${customer.variable_number}`
                : ''}
            </Text>
          </Stack>
          <Group gap="xs">
            <Anchor component={Link} to={`/c/${customer.id}`} size="sm">
              <Group gap={4} wrap="nowrap">
                <IconExternalLink size={16} aria-hidden />
                {t('users.open')}
              </Group>
            </Anchor>
            {assignsVs && (
              <Button
                size="xs"
                variant="default"
                onClick={() => {
                  onVariableNumber(customer);
                }}
              >
                {t('users.vs.button')}
              </Button>
            )}
            {manages && (
              <Button
                size="xs"
                leftSection={<IconUserPlus size={16} aria-hidden />}
                onClick={() => {
                  onInvite(customer);
                }}
              >
                {t('users.invite.button')}
              </Button>
            )}
          </Group>
        </Group>
        {logins.length === 0 ? (
          <Text size="sm" c="dimmed">
            {t('users.noLogins')}
          </Text>
        ) : (
          <ScrollTable label={`${t('users.login')}: ${customer.name}`} minWidth={560}>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('users.login')}</Table.Th>
                  <Table.Th>{t('users.role')}</Table.Th>
                  <Table.Th>{t('users.status')}</Table.Th>
                  {manages && <Table.Th>{t('users.actions')}</Table.Th>}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {logins.map((login) => (
                  <LoginRow
                    key={login.user_id}
                    me={me}
                    customer={customer}
                    login={login}
                    manages={manages}
                    onImpersonate={onImpersonate}
                  />
                ))}
              </Table.Tbody>
            </Table>
          </ScrollTable>
        )}
      </Stack>
    </Paper>
  );
}

export function LoginStatus({
  status,
  active,
  locked,
}: {
  status: string;
  active: boolean;
  locked: boolean;
}) {
  const { t } = useTranslation();
  if (!active) return <Badge color="gray">{t('status.inactive')}</Badge>;
  if (locked) return <Badge color="red">{t('status.locked')}</Badge>;
  const color = status === 'active' ? 'green' : status === 'invited' ? 'blue' : 'gray';
  return <Badge color={color}>{t(`status.${status}` as 'status.active')}</Badge>;
}

function LoginRow({
  me,
  customer,
  login,
  manages,
  onImpersonate,
}: {
  me: Me;
  customer: Customer;
  login: Login;
  manages: boolean;
  onImpersonate: (user: { id: string; name: string }) => void;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const act = useLoginAction();
  const [confirming, setConfirming] = useState(false);
  const run = (action: LoginAction) => {
    act.mutate(
      { customerId: customer.id, userId: login.user_id, action },
      {
        onSuccess: () => {
          notify.success(
            action === 'deactivate'
              ? t('users.login_actions.deactivated')
              : action === 'reactivate'
                ? t('users.login_actions.reactivated')
                : t('users.login_actions.linkSent'),
          );
          setConfirming(false);
        },
        onError: notify.failure,
      },
    );
  };
  const canImpersonate =
    onPlatform(me, 'users.impersonate') && login.status === 'active' && !login.locked;
  return (
    <Table.Tr>
      <Table.Td>
        <Text size="sm" fw={500}>
          {login.name}
        </Text>
        <Text size="xs" c="dimmed">
          {login.email}
        </Text>
      </Table.Td>
      <Table.Td>{t(`roles.${login.role}` as 'roles.customer_user')}</Table.Td>
      <Table.Td>
        <LoginStatus status={login.status} active={login.active} locked={login.locked} />
      </Table.Td>
      {manages && (
        <Table.Td>
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              <Button
                size="xs"
                variant="subtle"
                aria-label={`${t('users.actions')}: ${login.name}`}
                leftSection={<IconDots size={16} aria-hidden />}
              >
                {t('users.actions')}
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              {login.active ? (
                <Menu.Item
                  onClick={() => {
                    setConfirming(true);
                  }}
                >
                  {t('users.login_actions.deactivate')}
                </Menu.Item>
              ) : (
                <Menu.Item
                  onClick={() => {
                    run('reactivate');
                  }}
                >
                  {t('users.login_actions.reactivate')}
                </Menu.Item>
              )}
              <Menu.Item
                disabled={login.locked || login.status === 'deleted'}
                onClick={() => {
                  run('reset-link');
                }}
              >
                {t('users.login_actions.reset-link')}
              </Menu.Item>
              {canImpersonate && (
                <Menu.Item
                  onClick={() => {
                    onImpersonate({ id: login.user_id, name: login.name });
                  }}
                >
                  {t('users.user_actions.impersonate')}
                </Menu.Item>
              )}
            </Menu.Dropdown>
          </Menu>
          <ConfirmDialog
            opened={confirming}
            title={t('users.login_actions.deactivate')}
            message={t('users.login_actions.confirmDeactivate', {
              name: login.name,
              customer: customer.name,
            })}
            confirmLabel={t('users.login_actions.deactivate')}
            danger
            loading={act.isPending}
            onConfirm={() => {
              run('deactivate');
            }}
            onClose={() => {
              setConfirming(false);
            }}
          />
        </Table.Td>
      )}
    </Table.Tr>
  );
}
