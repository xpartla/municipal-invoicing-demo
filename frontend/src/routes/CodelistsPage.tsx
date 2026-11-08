import {
  Alert,
  Button,
  Group,
  Loader,
  Select,
  Stack,
  Tabs,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconHistory, IconPlus, IconSearch, IconUpload } from '@tabler/icons-react';
import { useParams } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Pager } from '../components/Pager';
import {
  useEditRow,
  useEntries,
  useListsOverview,
  useVersions,
  type Entry,
} from '../features/codelists/api';
import { EntryDialog } from '../features/codelists/EntryDialog';
import { EntryTable } from '../features/codelists/EntryTable';
import { HistoryDialog } from '../features/codelists/HistoryDialog';
import { CUSTOMER_TABS, FIELDS, type CustomerKind } from '../features/codelists/kinds';
import { useMe } from '../features/identity/api';
import { inCustomer } from '../features/identity/capabilities';
import { formatDateTime } from '../lib/format';
import { useNotify } from '../lib/notify';

const SIZE = 50;

/**
 * Číselníky (plan §10.6): the customer's lists for a year, one tab each, with a search that
 * ignores case and diacritics, any version of the year, and row editing (each edit makes a
 * new version). Users, staff and admins edit; viewers read.
 */
export function CodelistsPage() {
  const { t } = useTranslation();
  const { customerId } = useParams({ from: '/_app/c/$customerId' });
  const { data: me } = useMe();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [kind, setKind] = useState<CustomerKind>('budget_expense');
  const [query, setQuery] = useState('');
  const [debounced] = useDebouncedValue(query, 250);
  const [page, setPage] = useState(1);
  const [versionId, setVersionId] = useState<string | undefined>();
  const [dialog, setDialog] = useState<{ entry?: Entry } | undefined>();
  const [history, setHistory] = useState(false);
  const notify = useNotify();

  const overview = useListsOverview(customerId, year);
  const active = overview.data?.lists.find((l) => l.kind === kind)?.version ?? null;
  const versions = useVersions({ customerId }, kind, year, active !== null);
  const entries = useEntries(
    { customerId },
    kind,
    { year, version: versionId, q: debounced.trim(), page, size: SIZE },
    active !== null,
  );
  const edit = useEditRow(customerId, kind, year);
  const canEdit = me ? inCustomer(me, customerId, 'codelists.edit') : false;
  const viewing = entries.data?.version;
  const onActive = viewing === undefined || viewing.id === active?.id;
  const years = [...new Set([...(overview.data?.years ?? []), thisYear])].sort((a, b) => b - a);

  const choose = (next: CustomerKind) => {
    setKind(next);
    setPage(1);
    setVersionId(undefined);
  };
  const toggle = async (action: 'deactivate' | 'reactivate', entry: Entry) => {
    try {
      await edit.mutateAsync({ edit: { action, key: entry.key }, versionId: active?.id ?? null });
      notify.success(
        t(action === 'deactivate' ? 'codelists.deactivated' : 'codelists.reactivated'),
      );
    } catch (error) {
      notify.failure(error);
    }
  };

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Title order={1}>{t('codelists.title')}</Title>
        <Group gap="sm" align="flex-end">
          <Select
            label={t('codelists.year')}
            data={years.map((y) => ({ value: String(y), label: String(y) }))}
            value={String(year)}
            allowDeselect={false}
            onChange={(value) => {
              if (!value) return;
              setYear(Number(value));
              setPage(1);
              setVersionId(undefined);
            }}
            w={110}
          />
          <Tooltip label={t('codelists.importSoon')} withArrow>
            <div>
              <Button leftSection={<IconUpload size={16} aria-hidden />} disabled>
                {t('codelists.import')}
              </Button>
            </div>
          </Tooltip>
        </Group>
      </Group>
      <Tabs
        value={kind}
        onChange={(value) => {
          if (value) choose(value as CustomerKind);
        }}
        keepMounted={false}
      >
        <Tabs.List>
          {CUSTOMER_TABS.map((tab) => (
            <Tabs.Tab key={tab} value={tab}>
              {t(`codelists.kinds.${tab}`)}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>
      <Text maw={880}>{t(`codelists.notes.${kind}`)}</Text>
      {overview.isPending ? (
        <Loader aria-label={t('common.loading')} />
      ) : active === null ? (
        <Stack gap="sm" align="flex-start">
          <Text>{t('codelists.noList', { year })}</Text>
          {canEdit && (
            <Button
              leftSection={<IconPlus size={16} aria-hidden />}
              onClick={() => {
                setDialog({});
              }}
            >
              {t('codelists.add')}
            </Button>
          )}
        </Stack>
      ) : (
        <>
          <Group gap="sm" align="flex-end" wrap="wrap">
            <TextInput
              label={t('codelists.search')}
              leftSection={<IconSearch size={16} aria-hidden />}
              value={query}
              onChange={(event) => {
                setQuery(event.currentTarget.value);
                setPage(1);
              }}
              w={280}
              maw="100%"
            />
            <Select
              label={t('codelists.version')}
              data={(versions.data ?? []).map((v) => ({
                value: v.id,
                label: t('codelists.versionLabel', {
                  number: v.number,
                  date: formatDateTime(v.created_at),
                }),
              }))}
              value={versionId ?? active.id}
              allowDeselect={false}
              onChange={(value) => {
                setVersionId(value === active.id ? undefined : (value ?? undefined));
                setPage(1);
              }}
              w={260}
              maw="100%"
            />
            <Button
              variant="default"
              leftSection={<IconHistory size={16} aria-hidden />}
              onClick={() => {
                setHistory(true);
              }}
            >
              {t('codelists.historyButton')}
            </Button>
            {canEdit && onActive && (
              <Button
                leftSection={<IconPlus size={16} aria-hidden />}
                onClick={() => {
                  setDialog({});
                }}
              >
                {t('codelists.add')}
              </Button>
            )}
          </Group>
          {viewing && !onActive && (
            <Alert color="yellow">
              {t('codelists.oldVersion', { number: viewing.number, active: active.number })}
            </Alert>
          )}
          {entries.isPending ? (
            <Loader aria-label={t('common.loading')} />
          ) : entries.data?.items.length ? (
            <>
              <Text size="sm">{t('codelists.count', { count: entries.data.total })}</Text>
              <EntryTable
                label={t(`codelists.kinds.${kind}`)}
                fields={FIELDS[kind]}
                entries={entries.data.items}
                onAction={
                  canEdit && onActive
                    ? (action, entry) => {
                        if (action === 'edit') setDialog({ entry });
                        else void toggle(action, entry);
                      }
                    : undefined
                }
              />
              <Pager page={page} pages={Math.ceil(entries.data.total / SIZE)} onPage={setPage} />
            </>
          ) : (
            <Text>{debounced ? t('codelists.noMatch') : t('codelists.empty')}</Text>
          )}
        </>
      )}
      <EntryDialog
        customerId={customerId}
        kind={kind}
        year={year}
        versionId={active?.id ?? null}
        entry={dialog?.entry}
        opened={dialog !== undefined}
        onClose={() => {
          setDialog(undefined);
        }}
      />
      <HistoryDialog
        customerId={customerId}
        kind={kind}
        year={year}
        opened={history}
        onClose={() => {
          setHistory(false);
        }}
      />
    </Stack>
  );
}
