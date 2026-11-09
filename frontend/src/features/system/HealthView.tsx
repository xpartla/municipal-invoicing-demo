import { Anchor, Badge, Group, Loader, Stack, Table, Text } from '@mantine/core';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import { isCustomerKind } from '../codelists/kinds';
import { useHealth, type HealthFinding } from './api';

const COLOR = { error: 'red', warning: 'yellow', info: 'gray' } as const;

/** Kontrola znalostí (plan §6.5): what keeps the engine from proposing, or makes it propose
 * something the lists lack, each with a link to the list or the conventions concerned. */
export function HealthView({
  customerId,
  year,
  onConventions,
}: {
  customerId: string;
  year: number;
  /** Opens the conventions tab. */
  onConventions: () => void;
}) {
  const { t } = useTranslation();
  const health = useHealth(customerId, year);
  if (health.isPending) return <Loader aria-label={t('common.loading')} />;
  const report = health.data;
  if (!report) return null;
  const notes = report.findings.length - report.errors - report.warnings;
  return (
    <Stack gap="md">
      <Text>{t('system.health.intro')}</Text>
      <Group gap="sm">
        <Badge color="red">{t('system.health.errors', { count: report.errors })}</Badge>
        <Badge color="yellow">{t('system.health.warnings', { count: report.warnings })}</Badge>
        <Badge color="gray">{t('system.health.notes', { count: notes })}</Badge>
      </Group>
      {report.findings.length === 0 ? (
        <Text>{t('system.health.none')}</Text>
      ) : (
        <ScrollTable label={t('system.health.title')} minWidth={640}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('system.health.severity')}</Table.Th>
                <Table.Th>{t('system.health.finding')}</Table.Th>
                <Table.Th>{t('system.health.where')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {report.findings.map((finding, index) => (
                <Table.Tr key={`${finding.code}-${finding.subject}-${String(index)}`}>
                  <Table.Td>
                    <Badge color={COLOR[finding.severity]}>
                      {t(`system.health.severities.${finding.severity}`)}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{describe(finding, year, t)}</Table.Td>
                  <Table.Td>
                    <Where
                      finding={finding}
                      customerId={customerId}
                      year={year}
                      onConventions={onConventions}
                    />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}
    </Stack>
  );
}

type T = ReturnType<typeof useTranslation>['t'];

function place(where: string | null | undefined, t: T): string {
  if (!where) return '';
  if (where === 'canteen') return t('system.health.canteen');
  const [side, su] = where.split(' ');
  if (side === 'debit') return t('system.health.debit', { su });
  if (side === 'credit') return t('system.health.credit', { su });
  return where;
}

function describe(finding: HealthFinding, year: number, t: T): string {
  const list = (kind: string) => t(`codelists.kinds.${kind}` as 'codelists.kinds.accounts');
  const values = {
    year,
    subject: finding.subject,
    count: finding.count,
    where: place(finding.where, t),
    list: finding.kind ? list(finding.kind) : finding.subject,
  };
  return t(`system.health.codes.${finding.code}`, values);
}

function Where({
  finding,
  customerId,
  year,
  onConventions,
}: {
  finding: HealthFinding;
  customerId: string;
  year: number;
  onConventions: () => void;
}) {
  const { t } = useTranslation();
  const convention = finding.code.startsWith('convention_');
  if (convention) {
    return (
      <Anchor component="button" type="button" onClick={onConventions}>
        {t('system.health.openConventions')}
      </Anchor>
    );
  }
  const kind = finding.kind;
  if (kind && isCustomerKind(kind)) {
    const q = finding.code === 'list_missing' ? undefined : finding.subject;
    return (
      <Anchor
        renderRoot={(props) => (
          <Link
            {...props}
            to="/c/$customerId/codelists"
            params={{ customerId }}
            search={{ kind, year, q }}
          />
        )}
      >
        {t('system.health.openList', { list: t(`codelists.kinds.${kind}`) })}
      </Anchor>
    );
  }
  return <Text size="sm">{place(finding.where, t)}</Text>;
}
