import { Button, Group, Stack, TagsInput, Text, TextInput } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '../../components/Dialog';
import { emptyRule, type Rule } from './document';

const LISTS = ['concepts', 'function', 'ek', 'zdroj', 'terms'] as const;

/** One analytic-account rule: the AU it names and the conditions that must all hold (each
 * list matches any of its items; an empty list does not constrain). */
export function RuleDialog({
  su,
  rule,
  onClose,
  onSave,
}: {
  su: string;
  rule: Rule | undefined;
  onClose: () => void;
  onSave: (rule: Rule) => void;
}) {
  const { t } = useTranslation();
  // Mounted per rule (a key), so the draft starts from the rule being edited.
  const [draft, setDraft] = useState<Rule>(rule ?? emptyRule());
  const validAu = /^\d{3}$/.test(draft.au);
  return (
    <Dialog
      opened
      onClose={onClose}
      size="lg"
      title={
        rule ? t('system.conventions.rule.edit', { su }) : t('system.conventions.rule.add', { su })
      }
    >
      <Stack gap="sm">
        <Text size="sm">{t('system.conventions.rule.intro')}</Text>
        <TextInput
          label={t('system.conventions.au')}
          required
          value={draft.au}
          error={draft.au !== '' && !validAu ? t('codelists.digits', { count: 3 }) : undefined}
          onChange={(event) => {
            setDraft({ ...draft, au: event.currentTarget.value.trim() });
          }}
          w={160}
        />
        {LISTS.map((name) => (
          <TagsInput
            key={name}
            label={t(`system.conventions.conditions.${name}`)}
            description={t(`system.conventions.rule.hints.${name}`)}
            value={draft[name]}
            onChange={(value) => {
              setDraft({ ...draft, [name]: value });
            }}
          />
        ))}
        <TextInput
          label={t('system.conventions.note')}
          value={draft.note ?? ''}
          onChange={(event) => {
            const note = event.currentTarget.value;
            setDraft({ ...draft, note: note.trim() === '' ? null : note });
          }}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={!validAu}
            onClick={() => {
              onSave(draft);
            }}
          >
            {t('system.conventions.rule.apply')}
          </Button>
        </Group>
      </Stack>
    </Dialog>
  );
}
