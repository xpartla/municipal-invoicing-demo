import { Button, Group, NumberInput, Select, Stack, Table, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import type { ImportPreview, ReadOptions } from './api';

interface Props {
  preview: ImportPreview;
  options: ReadOptions;
  onOptions: (options: ReadOptions) => void;
  onNext: () => void;
  loading: boolean;
}

const ENCODINGS = ['utf-8', 'windows-1250'] as const;
const DELIMITERS = [';', ',', '\t', '|'] as const;

/** Step 2: how the file reads. The sheet, the header row, and for CSV the encoding and
 * the delimiter are detected; each can be chosen, and the preview follows. */
export function ReadStep({ preview, options, onOptions, onNext, loading }: Props) {
  const { t } = useTranslation();
  const csv = preview.format === 'csv';
  const width = Math.max(preview.columns.length, ...preview.rows.map((r) => r.cells.length), 1);
  const headerRow = options.header_row ?? preview.header_row;

  return (
    <Stack gap="md">
      <Group gap="md" align="flex-end" wrap="wrap">
        {preview.sheets.length > 1 && (
          <Select
            label={t('exchange.read.sheet')}
            data={preview.sheets}
            value={options.sheet ?? preview.sheet}
            allowDeselect={false}
            onChange={(sheet) => {
              onOptions({ ...options, sheet, header_row: null });
            }}
          />
        )}
        <NumberInput
          label={t('exchange.read.headerRow')}
          description={t('exchange.read.headerRowHint')}
          min={0}
          max={30}
          value={headerRow}
          onChange={(value) => {
            if (typeof value === 'number') onOptions({ ...options, header_row: value });
          }}
          w={180}
        />
        {csv && (
          <Select
            label={t('exchange.read.encoding')}
            data={ENCODINGS.map((e) => ({ value: e, label: t(`exchange.read.encodings.${e}`) }))}
            value={options.encoding ?? preview.encoding}
            allowDeselect={false}
            onChange={(value) => {
              onOptions({ ...options, encoding: value as ReadOptions['encoding'] });
            }}
            w={200}
          />
        )}
        {csv && (
          <Select
            label={t('exchange.read.delimiter')}
            data={DELIMITERS.map((d) => ({
              value: d,
              label: t(`exchange.read.delimiters.${d === '\t' ? 'tab' : d}`),
            }))}
            value={options.delimiter ?? preview.delimiter}
            allowDeselect={false}
            onChange={(value) => {
              onOptions({ ...options, delimiter: value as ReadOptions['delimiter'] });
            }}
            w={200}
          />
        )}
      </Group>
      <Text size="sm">
        {t('exchange.read.summary', {
          format: preview.format.toUpperCase(),
          rows: preview.data_rows,
          columns: preview.columns.length,
        })}
      </Text>
      <ScrollTable label={t('exchange.read.previewLabel')} minWidth={Math.min(140 * width, 1400)}>
        <Table striped withTableBorder fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th scope="col">{t('exchange.read.row')}</Table.Th>
              {preview.columns.map((column) => (
                <Table.Th key={column.key} scope="col">
                  <Text span fz="xs" c="dimmed">
                    {column.letter}
                  </Text>{' '}
                  {column.header || t('exchange.read.noHeader')}
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {preview.rows.map((row) => (
              <Table.Tr key={row.number}>
                <Table.Td>{row.number}</Table.Td>
                {Array.from({ length: preview.columns.length }, (_, i) => (
                  <Table.Td key={i}>{row.cells[i] ?? ''}</Table.Td>
                ))}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollTable>
      {preview.preamble.length > 0 && (
        <Text size="sm" c="dimmed">
          {t('exchange.read.preamble', { count: preview.preamble.length })}{' '}
          {preview.preamble
            .map((row) => row.filter(Boolean).join(' · '))
            .filter(Boolean)
            .join(' / ')}
        </Text>
      )}
      <Group>
        <Button onClick={onNext} loading={loading}>
          {t('exchange.read.next')}
        </Button>
      </Group>
    </Stack>
  );
}
