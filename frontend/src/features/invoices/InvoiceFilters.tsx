import {
  Badge,
  Button,
  Checkbox,
  Collapse,
  Group,
  MultiSelect,
  Select,
  SimpleGrid,
  Stack,
  TextInput,
} from '@mantine/core';
import { useDebouncedCallback, useDebouncedValue } from '@mantine/hooks';
import { IconFilter, IconSearch, IconX } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSeriesCodes, useSuppliers } from './api';
import { activeFilters, CHANNELS, DATE_FILTERS, STATES, type InvoiceSearch } from './search';

type Change = Partial<InvoiceSearch>;

/** A text input that writes its value after the user stops typing, and follows the URL. */
function LazyInput({
  value,
  onCommit,
  ...props
}: {
  value: string | undefined;
  onCommit: (value: string | undefined) => void;
} & Omit<React.ComponentProps<typeof TextInput>, 'value' | 'onChange'>) {
  const [text, setText] = useState(value ?? '');
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    // The URL changed under the input (filters cleared, back button): follow it.
    setShown(value);
    setText(value ?? '');
  }
  const commit = useDebouncedCallback((next: string) => {
    onCommit(next.trim() || undefined);
  }, 350);
  return (
    <TextInput
      {...props}
      value={text}
      onChange={(event) => {
        setText(event.currentTarget.value);
        commit(event.currentTarget.value);
      }}
    />
  );
}

const MORE: (keyof InvoiceSearch)[] = [
  'series',
  'channel',
  'mine',
  'amount_min',
  'amount_max',
  'budget',
  'md',
  'dal',
  ...DATE_FILTERS.flatMap((d) => [`${d}_from`, `${d}_to`] as const),
];

/** The invoice table's filters (plan §10.3); each change goes to the URL. */
export function InvoiceFilters({
  customerId,
  search,
  onChange,
}: {
  customerId: string;
  search: InvoiceSearch;
  onChange: (change: Change) => void;
}) {
  const { t } = useTranslation();
  const [more, setMore] = useState(() => MORE.some((k) => search[k] !== undefined));
  const [supplierText, setSupplierText] = useState('');
  const [supplierQuery] = useDebouncedValue(supplierText, 250);
  const suppliers = useSuppliers(customerId, supplierQuery.trim(), supplierQuery.trim() !== '');
  const series = useSeriesCodes(customerId, new Date().getFullYear());
  const count = activeFilters(search);

  const supplierData = [
    ...(search.supplier_ico
      ? [{ value: search.supplier_ico, label: search.supplier ?? search.supplier_ico }]
      : []),
    ...(suppliers.data ?? [])
      .filter((s) => s.ico && s.ico !== search.supplier_ico)
      .map((s) => ({ value: s.ico ?? '', label: `${s.name ?? s.ico ?? ''} (${s.ico ?? ''})` })),
  ];
  const review = search.needs_review === undefined ? 'all' : search.needs_review ? 'yes' : 'no';

  return (
    <Stack gap="sm">
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm">
        <LazyInput
          label={t('invoices.filters.search')}
          placeholder={t('invoices.filters.searchPlaceholder')}
          leftSection={<IconSearch size={16} aria-hidden />}
          value={search.q}
          onCommit={(q) => {
            onChange({ q });
          }}
        />
        <Select
          label={t('invoices.filters.supplier')}
          placeholder={t('invoices.filters.supplierPlaceholder')}
          searchable
          clearable
          data={supplierData}
          value={search.supplier_ico ?? null}
          searchValue={supplierText}
          onSearchChange={setSupplierText}
          nothingFoundMessage={supplierQuery ? '—' : undefined}
          onChange={(ico, option) => {
            onChange({
              supplier_ico: ico ?? undefined,
              supplier: ico ? option?.label.replace(/ \(\d{8}\)$/, '') : undefined,
            });
          }}
        />
        <MultiSelect
          label={t('invoices.filters.state')}
          data={STATES.map((s) => ({ value: s, label: t(`invoices.states.${s}`) }))}
          value={search.state ?? []}
          clearable
          onChange={(state) => {
            onChange({ state: state.length ? state : undefined });
          }}
        />
        {/* A select, not a segmented control: three labels did not fit a quarter of the row. */}
        <Select
          label={t('invoices.filters.review')}
          value={review}
          allowDeselect={false}
          data={[
            { value: 'all', label: t('invoices.filters.reviewAll') },
            { value: 'yes', label: t('invoices.filters.reviewYes') },
            { value: 'no', label: t('invoices.filters.reviewNo') },
          ]}
          onChange={(value) => {
            onChange({ needs_review: value === 'all' || !value ? undefined : value === 'yes' });
          }}
        />
      </SimpleGrid>
      <Group justify="space-between">
        <Group gap="xs">
          <Button
            variant="subtle"
            size="xs"
            leftSection={<IconFilter size={14} aria-hidden />}
            aria-expanded={more}
            onClick={() => {
              setMore((open) => !open);
            }}
          >
            {more ? t('invoices.filters.fewer') : t('invoices.filters.more')}
          </Button>
          {count > 0 && <Badge>{t('invoices.filters.active', { count })}</Badge>}
        </Group>
        {count > 0 && (
          <Button
            variant="subtle"
            size="xs"
            leftSection={<IconX size={14} aria-hidden />}
            onClick={() => {
              onChange(Object.fromEntries(Object.keys(search).map((k) => [k, undefined])));
            }}
          >
            {t('invoices.filters.clear')}
          </Button>
        )}
      </Group>
      <Collapse expanded={more}>
        <Stack gap="sm">
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm">
            <MultiSelect
              label={t('invoices.filters.series')}
              data={[...new Set([...(series.data ?? []), ...(search.series ?? [])])]}
              value={search.series ?? []}
              clearable
              onChange={(value) => {
                onChange({ series: value.length ? value : undefined });
              }}
            />
            <MultiSelect
              label={t('invoices.filters.channel')}
              data={CHANNELS.map((c) => ({ value: c, label: t(`invoices.channels.${c}`) }))}
              value={search.channel ?? []}
              clearable
              onChange={(value) => {
                onChange({ channel: value.length ? value : undefined });
              }}
            />
            <LazyInput
              label={t('invoices.filters.amountMin')}
              inputMode="decimal"
              value={search.amount_min}
              onCommit={(amount_min) => {
                onChange({ amount_min: amount_min?.replace(',', '.') });
              }}
            />
            <LazyInput
              label={t('invoices.filters.amountMax')}
              inputMode="decimal"
              value={search.amount_max}
              onCommit={(amount_max) => {
                onChange({ amount_max: amount_max?.replace(',', '.') });
              }}
            />
            <LazyInput
              label={t('invoices.filters.budget')}
              placeholder={t('invoices.filters.budgetPlaceholder')}
              value={search.budget}
              onCommit={(budget) => {
                onChange({ budget });
              }}
            />
            <LazyInput
              label={t('invoices.filters.md')}
              value={search.md}
              onCommit={(md) => {
                onChange({ md });
              }}
            />
            <LazyInput
              label={t('invoices.filters.dal')}
              value={search.dal}
              onCommit={(dal) => {
                onChange({ dal });
              }}
            />
            <Checkbox
              mt="lg"
              label={t('invoices.filters.mine')}
              checked={search.mine ?? false}
              onChange={(event) => {
                onChange({ mine: event.currentTarget.checked || undefined });
              }}
            />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 2, sm: 4, lg: 6 }} spacing="sm">
            {DATE_FILTERS.flatMap((name) =>
              (['from', 'to'] as const).map((end) => {
                const key = `${name}_${end}` as const;
                return (
                  <TextInput
                    key={key}
                    type="date"
                    label={t(`invoices.filters.${end}`, {
                      what: t(`invoices.filters.dates.${name}`),
                    })}
                    value={search[key] ?? ''}
                    onChange={(event) => {
                      onChange({ [key]: event.currentTarget.value || undefined });
                    }}
                  />
                );
              }),
            )}
          </SimpleGrid>
        </Stack>
      </Collapse>
    </Stack>
  );
}
