import {
  Alert,
  Button,
  Fieldset,
  Group,
  List,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { formatAmount, formatAmountForCopy } from '../../lib/format';
import { keyParts, parseAmount, type Line, type Problem } from './coding';

export interface Option {
  value: string;
  label: string;
}

export interface EditorLists {
  positions: Option[];
  accounts: Option[];
  supplierAccounts: Option[];
  transfers: (Option & { zdroj: string })[];
}

/**
 * Opraviť a prijať (plan §10.4): the lines with codes only from the customer's lists (budget
 * positions, accounts, transfers). Picking a position brings MD, DAL, transfer and texts by
 * the rules or the supplier's precedent (`onPicked`). Lines can be added and removed. A code
 * outside the lists blocks saving; a total that differs from the invoice only warns.
 */
export function CorrectionEditor({
  lines,
  onLines,
  onPicked,
  lists,
  gross,
  problems,
  note,
  onNote,
}: {
  lines: Line[];
  onLines: (lines: Line[]) => void;
  onPicked: (index: number, key: string) => void;
  lists: EditorLists;
  gross: number | null;
  problems: { errors: Problem[]; warnings: Problem[] };
  note: string;
  onNote: (note: string) => void;
}) {
  const { t } = useTranslation();
  const set = (index: number, change: Partial<Line>) => {
    onLines(lines.map((line, i) => (i === index ? { ...line, ...change } : line)));
  };
  const total = lines.reduce((sum, line) => sum + (parseAmount(line.amount) ?? 0), 0);
  const add = () => {
    const rest = Math.round(((gross ?? 0) - total) * 100) / 100;
    onLines([
      ...lines,
      {
        key: '',
        md: '',
        dal: lines[0]?.dal ?? '321 000',
        amount: formatAmountForCopy(rest),
        budgetText: '',
        postingText: '',
        transfer: '',
        choice: '',
      },
    ]);
  };
  const text = (problem: Problem) =>
    t(`invoice.problems.${problem.key}` as 'invoice.problems.noLines', {
      ...problem.values,
      ...(problem.key === 'total'
        ? {
            total: formatAmount(Number(problem.values?.total)),
            gross: formatAmount(Number(problem.values?.gross)),
          }
        : {}),
    });

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="md">
        <Title order={2} size="h4">
          {t('invoice.correct.title')}
        </Title>
        <Text size="sm" c="dimmed">
          {t('invoice.correct.text')}
        </Text>
        {lines.map((line, i) => {
          const zdroj = keyParts(line.key).zdroj;
          const own = lists.transfers.filter((tr) => tr.zdroj === zdroj);
          const transfers = own.length ? own : lists.transfers;
          return (
            <Fieldset key={i} legend={t('invoice.correct.line', { n: i + 1 })}>
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
                <Select
                  label={t('invoice.correct.position')}
                  placeholder={t('invoice.correct.search')}
                  searchable
                  limit={50}
                  data={lists.positions}
                  value={line.key || null}
                  onChange={(key) => {
                    set(i, { key: key ?? '' });
                    if (key) onPicked(i, key);
                  }}
                  style={{ gridColumn: 'span 2' }}
                />
                <TextInput
                  label={t('invoice.correct.amount')}
                  inputMode="decimal"
                  value={line.amount}
                  onChange={(event) => {
                    set(i, { amount: event.currentTarget.value });
                  }}
                />
                <Select
                  label={t('invoice.correct.md')}
                  placeholder={t('invoice.correct.search')}
                  searchable
                  limit={50}
                  data={lists.accounts}
                  value={line.md || null}
                  onChange={(md) => {
                    set(i, { md: md ?? '' });
                  }}
                />
                <Select
                  label={t('invoice.correct.dal')}
                  placeholder={t('invoice.correct.search')}
                  searchable
                  limit={50}
                  data={lists.supplierAccounts}
                  value={line.dal || null}
                  onChange={(dal) => {
                    set(i, { dal: dal ?? '' });
                  }}
                />
                <Select
                  label={t('invoice.correct.transfer')}
                  data={[
                    { value: '', label: t('invoice.correct.noTransfer') },
                    ...transfers.map(({ value, label }) => ({ value, label })),
                  ]}
                  value={line.transfer}
                  allowDeselect={false}
                  onChange={(transfer) => {
                    set(i, { transfer: transfer ?? '' });
                  }}
                />
                <TextInput
                  label={t('invoice.correct.budgetText')}
                  value={line.budgetText}
                  onChange={(event) => {
                    set(i, { budgetText: event.currentTarget.value });
                  }}
                />
                <TextInput
                  label={t('invoice.correct.postingText')}
                  value={line.postingText}
                  onChange={(event) => {
                    set(i, { postingText: event.currentTarget.value });
                  }}
                />
              </SimpleGrid>
              {lines.length > 1 && (
                <Group justify="flex-end" mt="xs">
                  <Button
                    size="xs"
                    variant="subtle"
                    color="red"
                    leftSection={<IconTrash size={14} aria-hidden />}
                    onClick={() => {
                      onLines(lines.filter((_, j) => j !== i));
                    }}
                  >
                    {t('invoice.correct.removeLine', { n: i + 1 })}
                  </Button>
                </Group>
              )}
            </Fieldset>
          );
        })}
        <Group justify="space-between">
          <Button
            size="xs"
            variant="default"
            leftSection={<IconPlus size={14} aria-hidden />}
            onClick={add}
          >
            {t('invoice.correct.addLine')}
          </Button>
          <Text size="sm" c="dimmed">
            {t('invoice.correct.total', {
              total: formatAmount(total),
              gross: formatAmount(gross),
            })}
          </Text>
        </Group>
        {(problems.errors.length > 0 || problems.warnings.length > 0) && (
          <Alert color={problems.errors.length ? 'red' : 'yellow'}>
            <List size="sm">
              {[...problems.errors, ...problems.warnings].map((problem, i) => (
                <List.Item key={i}>{text(problem)}</List.Item>
              ))}
            </List>
          </Alert>
        )}
        <Textarea
          label={t('invoice.correct.note')}
          placeholder={t('invoice.correct.notePlaceholder')}
          autosize
          minRows={2}
          maxLength={500}
          value={note}
          onChange={(event) => {
            onNote(event.currentTarget.value);
          }}
        />
      </Stack>
    </Paper>
  );
}
