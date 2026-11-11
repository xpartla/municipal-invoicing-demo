import { Badge, Group, Select, Stack, Table, Tabs, Text, TextInput, Title } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconSearch, IconUpload } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Pager } from '../../components/Pager';
import { ButtonLink } from '../../components/RouterLinks';
import { ScrollTable } from '../../components/ScrollTable';
import { useEntries, useGlobalChecklist } from '../../features/codelists/api';
import { EntryTable } from '../../features/codelists/EntryTable';
import { GLOBAL_FIELDS, GLOBAL_TABS, type GlobalKind } from '../../features/codelists/kinds';
import { Loading, LoadFailed } from '../../components/QueryStates';

const SIZE = 50;

/**
 * Globálne číselníky (plan §6.1, §10.9): which global lists exist for which year, and each
 * list to read. They change by import (P2-M3); `data/global/<year>/README.md` names their
 * official sources.
 */
export function GlobalCodelistsPage() {
  const { t } = useTranslation();
  const checklist = useGlobalChecklist();
  const withLists = (checklist.data ?? []).filter((y) => y.lists.some((l) => l.version));
  const [year, setYear] = useState<number | undefined>();
  const shownYear = year ?? withLists.at(-1)?.year ?? new Date().getFullYear();
  const [kind, setKind] = useState<GlobalKind>('ek');
  const [query, setQuery] = useState('');
  const [debounced] = useDebouncedValue(query, 250);
  const [page, setPage] = useState(1);
  const present = checklist.data
    ?.find((y) => y.year === shownYear)
    ?.lists.find((l) => l.kind === kind)?.version;
  const entries = useEntries(
    'global',
    kind,
    { year: shownYear, q: debounced.trim(), page, size: SIZE },
    present !== undefined && present !== null,
  );

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <Title order={1}>{t('globalCodelists.title')}</Title>
        <ButtonLink
          to="/admin/codelists/import"
          search={{ type: kind, year: shownYear }}
          leftSection={<IconUpload size={16} aria-hidden />}
        >
          {t('codelists.import')}
        </ButtonLink>
      </Group>
      <Text maw={880}>{t('globalCodelists.intro')}</Text>
      <section aria-labelledby="checklist-title">
        <Title order={2} size="h3" id="checklist-title" mb="xs">
          {t('globalCodelists.checklist')}
        </Title>
        {checklist.isPending ? (
          <Loading />
        ) : checklist.isError ? (
          <LoadFailed error={checklist.error} onRetry={checklist.refetch} />
        ) : (
          <ScrollTable label={t('globalCodelists.checklistTable')} minWidth={640}>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('globalCodelists.year')}</Table.Th>
                  {GLOBAL_TABS.map((tab) => (
                    <Table.Th key={tab}>{t(`codelists.kinds.${tab}`)}</Table.Th>
                  ))}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {checklist.data.map((row) => (
                  <Table.Tr key={row.year}>
                    <Table.Th scope="row">{row.year}</Table.Th>
                    {GLOBAL_TABS.map((tab) => {
                      const version = row.lists.find((l) => l.kind === tab)?.version;
                      return (
                        <Table.Td key={tab}>
                          {version ? (
                            t('globalCodelists.rows', { count: version.entry_count })
                          ) : (
                            <Badge color="red">{t('globalCodelists.missing')}</Badge>
                          )}
                        </Table.Td>
                      );
                    })}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollTable>
        )}
      </section>
      <Tabs
        value={kind}
        onChange={(value) => {
          if (!value) return;
          setKind(value as GlobalKind);
          setPage(1);
        }}
        keepMounted={false}
      >
        <Tabs.List>
          {GLOBAL_TABS.map((tab) => (
            <Tabs.Tab key={tab} value={tab}>
              {t(`codelists.kinds.${tab}`)}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>
      <Text maw={880}>{t(`globalCodelists.notes.${kind}`)}</Text>
      <Stack gap="sm">
        <Select
          label={t('globalCodelists.year')}
          data={(checklist.data ?? []).map((y) => ({
            value: String(y.year),
            label: String(y.year),
          }))}
          value={String(shownYear)}
          allowDeselect={false}
          onChange={(value) => {
            if (!value) return;
            setYear(Number(value));
            setPage(1);
          }}
          w={110}
        />
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
      </Stack>
      {!present ? (
        <Text>{t('globalCodelists.none', { year: shownYear })}</Text>
      ) : entries.isPending ? (
        <Loading />
      ) : entries.isError ? (
        <LoadFailed error={entries.error} onRetry={entries.refetch} />
      ) : entries.data.items.length ? (
        <>
          <Text size="sm">{t('codelists.count', { count: entries.data.total })}</Text>
          <EntryTable
            label={t(`codelists.kinds.${kind}`)}
            fields={GLOBAL_FIELDS}
            entries={entries.data.items}
          />
          <Pager page={page} pages={Math.ceil(entries.data.total / SIZE)} onPage={setPage} />
        </>
      ) : (
        <Text>{t('codelists.noMatch')}</Text>
      )}
    </Stack>
  );
}
