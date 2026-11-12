import {
  Group,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  VisuallyHidden,
} from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { CopyRow, CopyValue } from '../../components/CopyButtons';
import { ScrollTable } from '../../components/ScrollTable';
import { formatAmount, formatAmountForCopy } from '../../lib/format';
import {
  budgetRow,
  KEY_PARTS,
  keyParts,
  parseAmount,
  postingRow,
  type Alternative,
  type Line,
} from './coding';

export interface Names {
  position: (key: string) => string;
  account: (key: string) => string;
}

/**
 * The coding laid out like TOPSET's two tabs (plan §10.4, as the demo's proposal page):
 * Zaúčtovanie záväzku and Rozpočet záväzku, each value with a copy button, each line copied as
 * a tab-separated row. Before booking, "Iná položka" swaps a whole line for an alternative.
 */
export function ProposalCards({
  lines,
  names,
  alternatives,
  onSwap,
}: {
  lines: Line[];
  names: Names;
  /** Offered only while the invoice can be booked by the caller. */
  alternatives: Alternative[] | null;
  onSwap: (index: number, choice: string) => void;
}) {
  const { t } = useTranslation();
  const copy = (what: string) => t('invoice.copy.what', { what });
  return (
    // Side by side only where both tables fit without scrolling (from 1408 px).
    <SimpleGrid cols={{ base: 1, xl: 2 }} spacing="md">
      <Paper withBorder p="md" radius="md">
        <Title order={2} size="h4" mb="sm">
          {t('invoice.posting.title')}
        </Title>
        <ScrollTable label={t('invoice.posting.title')} minWidth={480}>
          <Table verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">{t('invoice.posting.md')}</Table.Th>
                <Table.Th scope="col">{t('invoice.posting.dal')}</Table.Th>
                <Table.Th scope="col" style={{ textAlign: 'right' }}>
                  {t('invoice.posting.amount')}
                </Table.Th>
                <Table.Th scope="col">{t('invoice.posting.text')}</Table.Th>
                <Table.Th scope="col">
                  <VisuallyHidden>{t('invoice.copy.row')}</VisuallyHidden>
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {lines.map((line, i) => (
                <Table.Tr key={i}>
                  {(['md', 'dal'] as const).map((side) => (
                    <Table.Td key={side}>
                      <Group gap={4} wrap="nowrap">
                        <Text ff="monospace" size="sm" style={{ whiteSpace: 'nowrap' }}>
                          {line[side]}
                        </Text>
                        <CopyValue value={line[side]} label={copy(t(`invoice.posting.${side}`))} />
                      </Group>
                      <Text size="xs" c="dimmed">
                        {names.account(line[side])}
                      </Text>
                    </Table.Td>
                  ))}
                  <Table.Td style={{ textAlign: 'right' }}>
                    <Group gap={4} wrap="nowrap" justify="flex-end">
                      <Text size="sm">{formatAmount(parseAmount(line.amount))}</Text>
                      <CopyValue
                        value={formatAmountForCopy(parseAmount(line.amount))}
                        label={copy(t('invoice.posting.amount'))}
                      />
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      <Text size="sm">{line.postingText}</Text>
                      <CopyValue value={line.postingText} label={copy(t('invoice.posting.text'))} />
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <CopyRow
                      value={postingRow(line)}
                      label={t('invoice.copy.postingRow', { n: i + 1 })}
                    />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      </Paper>

      <Paper withBorder p="md" radius="md">
        <Title order={2} size="h4" mb="sm">
          {t('invoice.budget.title')}
        </Title>
        <Stack gap="md">
          {lines.map((line, i) => {
            const parts = keyParts(line.key);
            return (
              <Stack key={i} gap={6}>
                <Group gap="xs" wrap="nowrap" align="flex-end">
                  <Group
                    gap="sm"
                    role="group"
                    aria-label={t('invoice.budget.position', { key: line.key })}
                  >
                    {KEY_PARTS.map((part) => (
                      <Stack key={part} gap={0}>
                        <Text size="xs" c="dimmed">
                          {t(`invoice.budget.parts.${part}`)}
                        </Text>
                        <Text ff="monospace" fw={700}>
                          {parts[part]}
                        </Text>
                      </Stack>
                    ))}
                  </Group>
                  <CopyValue value={line.key} label={copy(line.key)} />
                </Group>
                <Text size="xs" c="dimmed">
                  {names.position(line.key)}
                </Text>
                <Group gap="lg">
                  <Group gap={4}>
                    <Text size="sm" c="dimmed">
                      {t('invoice.budget.amount')}
                    </Text>
                    <Text size="sm">{formatAmount(parseAmount(line.amount))}</Text>
                    <CopyValue
                      value={formatAmountForCopy(parseAmount(line.amount))}
                      label={copy(t('invoice.budget.amount'))}
                    />
                  </Group>
                  <Group gap={4}>
                    <Text size="sm" c="dimmed">
                      {t('invoice.budget.text')}
                    </Text>
                    <Text size="sm">{line.budgetText}</Text>
                    <CopyValue value={line.budgetText} label={copy(t('invoice.budget.text'))} />
                  </Group>
                  {line.transfer && (
                    <Group gap={4}>
                      <Text size="sm" c="dimmed">
                        {t('invoice.budget.transfer')}
                      </Text>
                      <Text size="sm" ff="monospace">
                        {line.transfer}
                      </Text>
                      <CopyValue value={line.transfer} label={copy(t('invoice.budget.transfer'))} />
                    </Group>
                  )}
                </Group>
                <Group gap="sm" align="flex-end">
                  <CopyRow
                    value={budgetRow(line)}
                    label={t('invoice.copy.budgetRow', { n: i + 1 })}
                  />
                  {alternatives && alternatives.length > 0 && (
                    <Select
                      size="xs"
                      label={t('invoice.alternatives.label', { n: i + 1 })}
                      value={line.choice}
                      allowDeselect={false}
                      onChange={(choice) => {
                        onSwap(i, choice ?? '');
                      }}
                      data={[
                        { value: '', label: t('invoice.alternatives.proposed') },
                        ...alternatives.map((a, index) => ({
                          value: String(index),
                          label: `${a.budget_key} · ${names.position(a.budget_key) !== '' ? names.position(a.budget_key) : (a.budget_text ?? '')} · MD ${a.md ?? '—'} · ${String(Math.round(a.score * 100))} %`,
                        })),
                      ]}
                      comboboxProps={{ width: 420, position: 'bottom-start' }}
                    />
                  )}
                </Group>
              </Stack>
            );
          })}
        </Stack>
      </Paper>
    </SimpleGrid>
  );
}
