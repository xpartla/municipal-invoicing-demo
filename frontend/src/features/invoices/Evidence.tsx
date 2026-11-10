import {
  Accordion,
  Badge,
  Group,
  List,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { useTranslation } from 'react-i18next';

import type { Proposal } from './coding';
import { checkName, engineText, formatPercent } from './engineText';

const CONFIDENCE = [
  'ek',
  'cofog',
  'zdroj',
  'analytika',
  'md',
  'dal',
  'booking_date',
  'document_number',
] as const;

/** "Prečo práve toto" (plan §10.4): the evidence per field with its source, the confidence
 * per field, the checks that passed and the warnings, in Slovak. Collapsed by default. */
export function Evidence({ proposal }: { proposal: Proposal }) {
  const { t } = useTranslation();
  const groups = new Map<string, NonNullable<Proposal['evidence']>>();
  const checks = proposal.validation.checks ?? [];
  const warnings = proposal.validation.warnings ?? [];
  for (const item of proposal.evidence ?? []) {
    groups.set(item.field, [...(groups.get(item.field) ?? []), item]);
  }
  const confidence = CONFIDENCE.filter((key) => proposal.confidence[key] != null);
  const field = (name: string) =>
    t(`invoice.evidence.fields.${name}` as 'invoice.evidence.fields.ek', { defaultValue: name });

  return (
    <Accordion variant="contained">
      <Accordion.Item value="why">
        <Accordion.Control>
          <Title order={2} size="h4">
            {t('invoice.evidence.title')}
          </Title>
        </Accordion.Control>
        <Accordion.Panel>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
            {[...groups].map(([name, items]) => (
              <Stack key={name} gap={4}>
                <Title order={3} size="h6">
                  {field(name)}
                </Title>
                <List size="sm" spacing={4}>
                  {items.map((item, i) => (
                    <List.Item key={i}>
                      <Group gap={6} wrap="nowrap" align="flex-start">
                        <Badge color="gray" size="sm" style={{ flexShrink: 0 }}>
                          {t(`invoice.evidence.sources.${item.source}`)}
                        </Badge>
                        <Text size="sm">{engineText(item.detail)}</Text>
                      </Group>
                    </List.Item>
                  ))}
                </List>
              </Stack>
            ))}
            <Stack gap={4}>
              <Title order={3} size="h6">
                {t('invoice.evidence.confidence')}
              </Title>
              <Table withRowBorders={false} verticalSpacing={2}>
                <Table.Tbody>
                  {confidence.map((key) => (
                    <Table.Tr key={key}>
                      <Table.Td>{field(key)}</Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>
                        {formatPercent(proposal.confidence[key] ?? 0)}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Stack>
            {checks.length > 0 && (
              <Stack gap={4}>
                <Title order={3} size="h6">
                  {t('invoice.evidence.checks')}
                </Title>
                <List size="sm">
                  {checks.map((check) => (
                    <List.Item key={check}>{checkName(check)}</List.Item>
                  ))}
                </List>
              </Stack>
            )}
            {warnings.length > 0 && (
              <Stack gap={4}>
                <Title order={3} size="h6">
                  {t('invoice.evidence.warnings')}
                </Title>
                <List size="sm">
                  {warnings.map((warning) => (
                    <List.Item key={warning}>{engineText(warning)}</List.Item>
                  ))}
                </List>
              </Stack>
            )}
          </SimpleGrid>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
