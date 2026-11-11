import { ActionIcon, Group, Select } from '@mantine/core';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { monthLabel, shiftMonth } from './dashboard';

const CHOICES = 24;

/**
 * The month picker of plan §10.2: the previous and the next month, and a list of the last
 * two years' months; nothing after `latest` (the current month).
 */
export function MonthPicker({
  value,
  latest,
  onChange,
}: {
  value: string;
  latest: string;
  onChange: (month: string) => void;
}) {
  const { t } = useTranslation();
  const months = Array.from({ length: CHOICES }, (_, n) => shiftMonth(latest, -n));
  if (!months.includes(value)) months.push(value);
  const previous = shiftMonth(value, -1);
  const next = shiftMonth(value, 1);
  return (
    <Group gap="xs" wrap="nowrap" align="flex-end">
      <ActionIcon
        variant="default"
        size="lg"
        aria-label={t('home.month.previous', { month: monthLabel(previous) })}
        onClick={() => {
          onChange(previous);
        }}
      >
        <IconChevronLeft size={18} aria-hidden />
      </ActionIcon>
      <Select
        label={t('home.month.label')}
        data={months.map((m) => ({ value: m, label: monthLabel(m) }))}
        value={value}
        allowDeselect={false}
        onChange={(chosen) => {
          if (chosen) onChange(chosen);
        }}
        w={180}
      />
      <ActionIcon
        variant="default"
        size="lg"
        disabled={value >= latest}
        aria-label={t('home.month.next', { month: monthLabel(next) })}
        onClick={() => {
          onChange(next);
        }}
      >
        <IconChevronRight size={18} aria-hidden />
      </ActionIcon>
    </Group>
  );
}
