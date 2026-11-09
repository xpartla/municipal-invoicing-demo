import { Alert, Button, Group, Select, Stack, TextInput, Title } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMe } from '../identity/api';
import { inAnyProvider, inCustomer, onPlatform } from '../identity/capabilities';
import { useSaveRunTemplate, type ImportRun, type Owner, type SavableScope } from './api';
import { useProblemText } from './problemText';

/** Step 5: the run's mapping as a template, for the customer, its service provider, or
 * everyone (plan §9.2 step 5), as far as the caller may make each (plan §5.2). */
export function TemplateSave({
  owner,
  run,
  suggestedName,
}: {
  owner: Owner;
  run: ImportRun;
  suggestedName?: string | null;
}) {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const problemText = useProblemText();
  const save = useSaveRunTemplate(owner, run.id);
  const scopes: SavableScope[] = [];
  if (me && owner !== 'global') {
    if (inCustomer(me, owner.customerId, 'templates.create_customer')) scopes.push('customer');
    if (inAnyProvider(me, 'templates.create_provider')) scopes.push('provider');
  }
  if (me && onPlatform(me, 'templates.create_global')) scopes.push('global');
  const [scope, setScope] = useState<SavableScope | undefined>(scopes[0]);
  const [name, setName] = useState(suggestedName ?? run.file.name.replace(/\.[^.]+$/, ''));
  const [problem, setProblem] = useState<string | null>(null);
  if (scopes.length === 0) return null;

  const submit = async () => {
    setProblem(null);
    if (!scope || !name.trim()) {
      setProblem(t('exchange.template.nameRequired'));
      return;
    }
    try {
      await save.mutateAsync({ scope, name: name.trim() });
    } catch (error) {
      setProblem(problemText(error));
    }
  };

  return (
    <Stack gap="sm" maw={560}>
      <Title order={2} size="h4">
        {t('exchange.template.title')}
      </Title>
      {save.isSuccess ? (
        <Alert color="green">{t('exchange.template.saved', { name: save.data.name })}</Alert>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <Stack gap="sm">
            <TextInput
              label={t('exchange.template.name')}
              description={t('exchange.template.nameHint')}
              value={name}
              maxLength={120}
              onChange={(event) => {
                setName(event.currentTarget.value);
              }}
              error={problem}
            />
            {scopes.length > 1 && (
              <Select
                label={t('exchange.template.scope')}
                data={scopes.map((s) => ({ value: s, label: t(`exchange.scopes.${s}`) }))}
                value={scope ?? null}
                allowDeselect={false}
                onChange={(value) => {
                  if (value) setScope(value);
                }}
              />
            )}
            <Group>
              <Button type="submit" variant="default" loading={save.isPending}>
                {t('exchange.template.save')}
              </Button>
            </Group>
          </Stack>
        </form>
      )}
    </Stack>
  );
}
