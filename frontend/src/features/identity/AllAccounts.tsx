import { Badge, Button, Group, Menu, Stack, Switch, Table, Text, TextInput } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconDots, IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import { useNotify } from '../../lib/notify';
import { useUserAction, useUsers, type Me, type UserAction, type UserInfo } from './api';
import { ImpersonateDialog } from './ImpersonateDialog';
import { Loading, LoadFailed } from '../../components/QueryStates';

/**
 * Všetky účty (plan §10.9, admins): every user with lock and unlock, a forced logout, delete,
 * restore, purge and impersonation. An admin's own account and other admins are not offered
 * the actions the API refuses for them.
 */
export function AllAccounts({ me }: { me: Me }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [debounced] = useDebouncedValue(query, 250);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const users = useUsers(debounced.trim(), includeDeleted);
  const [impersonate, setImpersonate] = useState<{ id: string; name: string } | null>(null);
  return (
    <Stack gap="sm">
      <Group gap="md" align="flex-end">
        <TextInput
          label={t('users.accounts.search')}
          leftSection={<IconSearch size={16} aria-hidden />}
          value={query}
          onChange={(event) => {
            setQuery(event.currentTarget.value);
          }}
          w={320}
          maw="100%"
        />
        <Switch
          label={t('users.accounts.includeDeleted')}
          checked={includeDeleted}
          onChange={(event) => {
            setIncludeDeleted(event.currentTarget.checked);
          }}
        />
      </Group>
      {users.isPending ? (
        <Loading />
      ) : users.isError ? (
        <LoadFailed error={users.error} onRetry={users.refetch} />
      ) : users.data.items.length ? (
        <ScrollTable label={t('users.tabs.accounts')} minWidth={640}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('users.accounts.name')}</Table.Th>
                <Table.Th>{t('users.accounts.memberships')}</Table.Th>
                <Table.Th>{t('users.status')}</Table.Th>
                <Table.Th>{t('users.actions')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {users.data.items.map((user) => (
                <AccountRow
                  key={user.id}
                  me={me}
                  user={user}
                  onImpersonate={() => {
                    setImpersonate({ id: user.id, name: user.name });
                  }}
                />
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      ) : (
        <Text>{t('users.accounts.none')}</Text>
      )}
      <ImpersonateDialog
        user={impersonate}
        onClose={() => {
          setImpersonate(null);
        }}
      />
    </Stack>
  );
}

const CONFIRMED: Partial<Record<UserAction, 'lock' | 'delete' | 'purge' | 'logout'>> = {
  lock: 'lock',
  delete: 'delete',
  purge: 'purge',
  logout: 'logout',
};

function AccountRow({
  me,
  user,
  onImpersonate,
}: {
  me: Me;
  user: UserInfo;
  onImpersonate: () => void;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const act = useUserAction();
  const [asking, setAsking] = useState<UserAction | null>(null);
  const self = user.id === (me.impersonation?.real_user_id ?? me.user.id);
  const isAdmin = user.memberships.some((m) => m.role === 'platform_admin' && m.active);
  const run = (action: UserAction) => {
    act.mutate(
      { userId: user.id, action },
      {
        onSuccess: () => {
          notify.success(t('users.user_actions.done'));
          setAsking(null);
        },
        onError: notify.failure,
      },
    );
  };
  const ask = (action: UserAction) => {
    if (CONFIRMED[action]) setAsking(action);
    else run(action);
  };
  const actions: UserAction[] = [];
  if (!self) {
    if (user.status === 'deleted') actions.push('restore', 'purge');
    else {
      actions.push(user.locked ? 'unlock' : 'lock', 'logout', 'delete');
    }
  }
  const confirmKey = asking ? CONFIRMED[asking] : undefined;
  return (
    <Table.Tr>
      <Table.Td>
        <Text size="sm" fw={500}>
          {user.name}
        </Text>
        <Text size="xs" c="dimmed">
          {user.email}
        </Text>
      </Table.Td>
      <Table.Td>
        <Group gap={4}>
          {user.memberships.map((m) => (
            <Badge key={m.id} color={m.active ? 'riso' : 'gray'}>
              {t(`roles.${m.role}` as 'roles.customer_user')}
            </Badge>
          ))}
        </Group>
      </Table.Td>
      <Table.Td>
        <Badge color={user.locked ? 'red' : user.status === 'active' ? 'green' : 'gray'}>
          {user.locked ? t('status.locked') : t(`status.${user.status}` as 'status.active')}
        </Badge>
      </Table.Td>
      <Table.Td>
        {(actions.length > 0 || (!isAdmin && user.status === 'active')) && (
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              <Button
                size="xs"
                variant="subtle"
                aria-label={`${t('users.actions')}: ${user.name}`}
                leftSection={<IconDots size={16} aria-hidden />}
              >
                {t('users.actions')}
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              {!isAdmin && !self && user.status === 'active' && !user.locked && (
                <Menu.Item onClick={onImpersonate}>{t('users.user_actions.impersonate')}</Menu.Item>
              )}
              {actions.map((action) => (
                <Menu.Item
                  key={action}
                  color={action === 'purge' || action === 'delete' ? 'red' : undefined}
                  onClick={() => {
                    ask(action);
                  }}
                >
                  {t(`users.user_actions.${action}`)}
                </Menu.Item>
              ))}
            </Menu.Dropdown>
          </Menu>
        )}
        {confirmKey && asking && (
          <ConfirmDialog
            opened
            title={t(`users.user_actions.${asking}`)}
            message={t(`users.user_actions.confirm.${confirmKey}`, { name: user.name })}
            confirmLabel={t(`users.user_actions.${asking}`)}
            danger={asking !== 'logout'}
            loading={act.isPending}
            onConfirm={() => {
              run(asking);
            }}
            onClose={() => {
              setAsking(null);
            }}
          />
        )}
      </Table.Td>
    </Table.Tr>
  );
}
