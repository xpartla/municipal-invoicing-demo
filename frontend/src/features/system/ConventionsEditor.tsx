import {
  ActionIcon,
  Alert,
  Button,
  Group,
  Paper,
  Stack,
  Switch,
  Table,
  TagsInput,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconArrowDown, IconArrowUp, IconPencil, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import { ApiError, fieldOf } from '../../lib/apiError';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import { useConventions, useSaveConventions } from './api';
import {
  conditions,
  normalise,
  type Canteen,
  type ConventionsDocument,
  type Rule,
  type Side,
} from './document';
import { RuleDialog } from './RuleDialog';
import { Loading, LoadFailed } from '../../components/QueryStates';

const SIDES: Side[] = ['debit', 'credit'];
const NEW_CANTEEN: Canteen = {
  concepts: ['food'],
  function: '09 601',
  zdroj: '',
  ek: '633011',
  analytika: '',
  alternatives: [],
  md: '',
};

/**
 * Účtovacie zvyklosti (plan §6.4, decision 56): the customer's own coding rules for the year,
 * edited as one document and saved with the revision it was loaded at. The rules of a
 * synthetic account apply in order: the first whose conditions all hold names the analytic
 * account, else its default does.
 */
export function ConventionsEditor({
  customerId,
  year,
  canEdit,
}: {
  customerId: string;
  year: number;
  canEdit: boolean;
}) {
  const conventions = useConventions(customerId, year);
  if (conventions.isError) {
    return <LoadFailed error={conventions.error} onRetry={conventions.refetch} />;
  }
  if (conventions.isPending) return <Loading />;
  const { revision, document } = conventions.data;
  return (
    <ConventionsForm
      // A new revision (saved here or reloaded after a conflict) starts the form afresh.
      key={`${String(year)}-${String(revision)}`}
      customerId={customerId}
      year={year}
      canEdit={canEdit}
      revision={revision}
      initial={normalise(document)}
      onReload={() => void conventions.refetch()}
    />
  );
}

function ConventionsForm({
  customerId,
  year,
  canEdit,
  revision,
  initial,
  onReload,
}: {
  customerId: string;
  year: number;
  canEdit: boolean;
  revision: number;
  initial: ConventionsDocument;
  onReload: () => void;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const errorText = useErrorText();
  const save = useSaveConventions(customerId, year);
  const [doc, setDoc] = useState<ConventionsDocument>(initial);
  const [dirty, setDirty] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  const [conflict, setConflict] = useState(false);
  const [editing, setEditing] = useState<{ side: Side; su: string; index?: number } | undefined>();
  const [newSu, setNewSu] = useState<Record<Side, string>>({ debit: '', credit: '' });
  const [newConcept, setNewConcept] = useState('');

  const change = (next: ConventionsDocument) => {
    setDoc(next);
    setDirty(true);
    setProblems([]);
  };
  const setSide = (side: Side, rules: ConventionsDocument['au_rules'][Side]) => {
    change({ ...doc, au_rules: { ...doc.au_rules, [side]: rules } });
  };
  const setRules = (side: Side, su: string, rules: Rule[]) => {
    const account = doc.au_rules[side][su];
    if (account) setSide(side, { ...doc.au_rules[side], [su]: { ...account, rules } });
  };
  const labels = {
    concepts: t('system.conventions.conditions.concepts'),
    function: t('system.conventions.conditions.function'),
    ek: t('system.conventions.conditions.ek'),
    zdroj: t('system.conventions.conditions.zdroj'),
    terms: t('system.conventions.conditions.terms'),
  };

  const submit = async () => {
    try {
      await save.mutateAsync({ revision, document: doc as unknown as Record<string, unknown> });
      notify.success(t('system.conventions.saved'));
      setConflict(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setConflict(true);
      } else if (error instanceof ApiError && error.status === 422) {
        setProblems(
          error.problems.map(
            (p) => `${fieldOf(p).replace(/^document\.?/, '')}: ${errorText(p.type, p.msg)}`,
          ),
        );
      } else {
        notify.failure(error);
      }
    }
  };

  const editingIndex = editing?.index;
  const editingRule =
    editing && editingIndex !== undefined
      ? doc.au_rules[editing.side][editing.su]?.rules[editingIndex]
      : undefined;

  return (
    <Stack gap="lg">
      <Text maw={880}>{t('system.conventions.intro')}</Text>
      {SIDES.map((side) => {
        const accounts = Object.keys(doc.au_rules[side]).sort();
        return (
          <section key={side} aria-labelledby={`rules-${side}`}>
            <Title order={2} size="h3" id={`rules-${side}`} mb="xs">
              {t(`system.conventions.sides.${side}`)}
            </Title>
            <Stack gap="md">
              {accounts.length === 0 && <Text>{t('system.conventions.noRules')}</Text>}
              {accounts.map((su) => {
                const account = doc.au_rules[side][su];
                if (!account) return null;
                return (
                  <Paper key={su} withBorder p="md">
                    <Stack gap="sm">
                      <Group justify="space-between" align="flex-end">
                        <Group align="flex-end" gap="sm">
                          <Title order={3} size="h4">
                            {t('system.conventions.account', { su })}
                          </Title>
                          <TextInput
                            label={t('system.conventions.default')}
                            value={account.default}
                            readOnly={!canEdit}
                            w={140}
                            onChange={(event) => {
                              setSide(side, {
                                ...doc.au_rules[side],
                                [su]: { ...account, default: event.currentTarget.value.trim() },
                              });
                            }}
                          />
                        </Group>
                        {canEdit && (
                          <Button
                            variant="subtle"
                            color="red"
                            onClick={() => {
                              setSide(side, without(doc.au_rules[side], su));
                            }}
                          >
                            {t('system.conventions.removeAccount', { su })}
                          </Button>
                        )}
                      </Group>
                      {account.rules.length > 0 && (
                        <ScrollTable label={t('system.conventions.rulesOf', { su })} minWidth={560}>
                          <Table striped>
                            <Table.Thead>
                              <Table.Tr>
                                <Table.Th>{t('system.conventions.order')}</Table.Th>
                                <Table.Th>{t('system.conventions.au')}</Table.Th>
                                <Table.Th>{t('system.conventions.when')}</Table.Th>
                                <Table.Th>{t('system.conventions.note')}</Table.Th>
                                {canEdit && <Table.Th>{t('codelists.actions')}</Table.Th>}
                              </Table.Tr>
                            </Table.Thead>
                            <Table.Tbody>
                              {account.rules.map((rule, index) => (
                                <Table.Tr key={`${rule.au}-${String(index)}`}>
                                  <Table.Td>{index + 1}</Table.Td>
                                  <Table.Td ff="monospace">{rule.au}</Table.Td>
                                  <Table.Td>
                                    {conditions(rule, labels) || t('system.conventions.always')}
                                  </Table.Td>
                                  <Table.Td>{rule.note ?? ''}</Table.Td>
                                  {canEdit && (
                                    <Table.Td>
                                      <Group gap={4} wrap="nowrap">
                                        <ActionIcon
                                          variant="subtle"
                                          disabled={index === 0}
                                          aria-label={t('system.conventions.up', {
                                            su,
                                            n: index + 1,
                                          })}
                                          onClick={() => {
                                            setRules(
                                              side,
                                              su,
                                              move(account.rules, index, index - 1),
                                            );
                                          }}
                                        >
                                          <IconArrowUp size={16} aria-hidden />
                                        </ActionIcon>
                                        <ActionIcon
                                          variant="subtle"
                                          disabled={index === account.rules.length - 1}
                                          aria-label={t('system.conventions.down', {
                                            su,
                                            n: index + 1,
                                          })}
                                          onClick={() => {
                                            setRules(
                                              side,
                                              su,
                                              move(account.rules, index, index + 1),
                                            );
                                          }}
                                        >
                                          <IconArrowDown size={16} aria-hidden />
                                        </ActionIcon>
                                        <ActionIcon
                                          variant="subtle"
                                          aria-label={t('system.conventions.editRule', {
                                            su,
                                            n: index + 1,
                                          })}
                                          onClick={() => {
                                            setEditing({ side, su, index });
                                          }}
                                        >
                                          <IconPencil size={16} aria-hidden />
                                        </ActionIcon>
                                        <ActionIcon
                                          variant="subtle"
                                          color="red"
                                          aria-label={t('system.conventions.removeRule', {
                                            su,
                                            n: index + 1,
                                          })}
                                          onClick={() => {
                                            setRules(
                                              side,
                                              su,
                                              account.rules.filter((_, i) => i !== index),
                                            );
                                          }}
                                        >
                                          <IconTrash size={16} aria-hidden />
                                        </ActionIcon>
                                      </Group>
                                    </Table.Td>
                                  )}
                                </Table.Tr>
                              ))}
                            </Table.Tbody>
                          </Table>
                        </ScrollTable>
                      )}
                      {canEdit && (
                        <Group>
                          <Button
                            variant="default"
                            size="xs"
                            onClick={() => {
                              setEditing({ side, su });
                            }}
                          >
                            {t('system.conventions.addRule', { su })}
                          </Button>
                        </Group>
                      )}
                    </Stack>
                  </Paper>
                );
              })}
              {canEdit && (
                <Group align="flex-end" gap="sm">
                  <TextInput
                    label={t('system.conventions.newAccount')}
                    value={newSu[side]}
                    w={200}
                    onChange={(event) => {
                      setNewSu({ ...newSu, [side]: event.currentTarget.value });
                    }}
                  />
                  <Button
                    variant="default"
                    disabled={
                      !/^\d{3}$/.test(newSu[side].trim()) ||
                      newSu[side].trim() in doc.au_rules[side]
                    }
                    onClick={() => {
                      setSide(side, {
                        ...doc.au_rules[side],
                        [newSu[side].trim()]: { default: '000', rules: [] },
                      });
                      setNewSu({ ...newSu, [side]: '' });
                    }}
                  >
                    {t('system.conventions.addAccount')}
                  </Button>
                </Group>
              )}
            </Stack>
          </section>
        );
      })}

      <section aria-labelledby="canteen">
        <Title order={2} size="h3" id="canteen" mb="xs">
          {t('system.conventions.canteen.title')}
        </Title>
        <Stack gap="sm" maw={720}>
          <Text>{t('system.conventions.canteen.intro')}</Text>
          <Switch
            label={t('system.conventions.canteen.enabled')}
            checked={doc.canteen !== null}
            disabled={!canEdit}
            onChange={(event) => {
              change({ ...doc, canteen: event.currentTarget.checked ? NEW_CANTEEN : null });
            }}
          />
          {doc.canteen && (
            <Group align="flex-start" gap="sm" wrap="wrap">
              {(['function', 'ek', 'zdroj', 'analytika', 'md'] as const).map((name) => (
                <TextInput
                  key={name}
                  label={t(`system.conventions.canteen.fields.${name}`)}
                  value={doc.canteen?.[name] ?? ''}
                  readOnly={!canEdit}
                  w={150}
                  onChange={(event) => {
                    if (doc.canteen)
                      change({
                        ...doc,
                        canteen: { ...doc.canteen, [name]: event.currentTarget.value },
                      });
                  }}
                />
              ))}
              <TagsInput
                label={t('system.conventions.canteen.fields.alternatives')}
                value={doc.canteen.alternatives}
                readOnly={!canEdit}
                w={240}
                onChange={(alternatives) => {
                  if (doc.canteen) change({ ...doc, canteen: { ...doc.canteen, alternatives } });
                }}
              />
              <TagsInput
                label={t('system.conventions.canteen.fields.concepts')}
                value={doc.canteen.concepts}
                readOnly={!canEdit}
                w={240}
                onChange={(concepts) => {
                  if (doc.canteen) change({ ...doc, canteen: { ...doc.canteen, concepts } });
                }}
              />
            </Group>
          )}
        </Stack>
      </section>

      <section aria-labelledby="concepts">
        <Title order={2} size="h3" id="concepts" mb="xs">
          {t('system.conventions.concepts.title')}
        </Title>
        <Stack gap="sm" maw={880}>
          <Text>{t('system.conventions.concepts.intro')}</Text>
          {Object.entries(doc.concepts).map(([name, concept]) => (
            <Group key={name} align="flex-end" gap="sm" wrap="wrap">
              <TextInput
                label={t('system.conventions.concepts.name')}
                value={name}
                readOnly
                w={200}
              />
              <TagsInput
                label={t('system.conventions.concepts.terms', { name })}
                value={concept.terms}
                readOnly={!canEdit}
                w={360}
                maw="100%"
                onChange={(terms) => {
                  change({ ...doc, concepts: { ...doc.concepts, [name]: { ...concept, terms } } });
                }}
              />
              {canEdit && (
                <Button
                  variant="subtle"
                  color="red"
                  onClick={() => {
                    change({ ...doc, concepts: without(doc.concepts, name) });
                  }}
                >
                  {t('system.conventions.concepts.remove', { name })}
                </Button>
              )}
            </Group>
          ))}
          {canEdit && (
            <Group align="flex-end" gap="sm">
              <TextInput
                label={t('system.conventions.concepts.new')}
                value={newConcept}
                w={200}
                onChange={(event) => {
                  setNewConcept(event.currentTarget.value);
                }}
              />
              <Button
                variant="default"
                disabled={
                  !/^[a-z][a-z0-9_]*$/.test(newConcept.trim()) || newConcept.trim() in doc.concepts
                }
                onClick={() => {
                  change({
                    ...doc,
                    concepts: {
                      ...doc.concepts,
                      [newConcept.trim()]: { terms: [], ek: [], weight: 1, text: null },
                    },
                  });
                  setNewConcept('');
                }}
              >
                {t('system.conventions.concepts.add')}
              </Button>
            </Group>
          )}
        </Stack>
      </section>

      <section aria-labelledby="transfers">
        <Title order={2} size="h3" id="transfers" mb="xs">
          {t('system.conventions.transfers.title')}
        </Title>
        <TagsInput
          label={t('system.conventions.transfers.never')}
          description={t('system.conventions.transfers.hint')}
          value={doc.transfers.never}
          readOnly={!canEdit}
          maw={480}
          onChange={(never) => {
            change({ ...doc, transfers: { never } });
          }}
        />
      </section>

      {problems.length > 0 && (
        <Alert color="red" role="alert" title={t('system.conventions.invalid')}>
          {problems.map((problem) => (
            <Text key={problem} size="sm">
              {problem}
            </Text>
          ))}
        </Alert>
      )}
      {conflict && (
        <Alert color="red" role="alert">
          <Stack gap="xs" align="flex-start">
            <Text size="sm">{t('system.conventions.conflict')}</Text>
            <Button
              size="xs"
              variant="default"
              onClick={() => {
                setConflict(false);
                onReload();
              }}
            >
              {t('system.conventions.reload')}
            </Button>
          </Stack>
        </Alert>
      )}
      <Group>
        <Text size="sm">{t('system.conventions.revision', { revision })}</Text>
        {canEdit && (
          <>
            <Button loading={save.isPending} disabled={!dirty} onClick={() => void submit()}>
              {t('system.conventions.save')}
            </Button>
            <Button
              variant="default"
              disabled={!dirty}
              onClick={() => {
                setDoc(initial);
                setDirty(false);
                setProblems([]);
              }}
            >
              {t('system.conventions.discard')}
            </Button>
          </>
        )}
      </Group>

      {editing && (
        <RuleDialog
          key={`${editing.side}-${editing.su}-${String(editing.index ?? 'new')}`}
          su={editing.su}
          rule={editingRule}
          onClose={() => {
            setEditing(undefined);
          }}
          onSave={(rule) => {
            const account = doc.au_rules[editing.side][editing.su];
            if (!account) return;
            const rules =
              editing.index === undefined
                ? [...account.rules, rule]
                : account.rules.map((r, i) => (i === editing.index ? rule : r));
            setRules(editing.side, editing.su, rules);
            setEditing(undefined);
          }}
        />
      )}
    </Stack>
  );
}

/** The list with the item at `from` moved to `to`. */
function move<T>(list: readonly T[], from: number, to: number): T[] {
  const result = [...list];
  const [item] = result.splice(from, 1);
  if (item !== undefined) result.splice(to, 0, item);
  return result;
}

/** The record without the key. */
function without<T>(record: Record<string, T>, key: string): Record<string, T> {
  return Object.fromEntries(Object.entries(record).filter(([name]) => name !== key));
}
