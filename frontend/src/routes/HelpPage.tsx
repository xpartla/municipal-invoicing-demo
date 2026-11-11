import { Card, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { AnchorLink } from '../components/RouterLinks';
import { useMe, type Me } from '../features/identity/api';
import { onPlatform, seesProviderScreens } from '../features/identity/capabilities';
import { allArticles } from '../help/articles';
import { HELP_GROUPS, type HelpGroup } from '../help/topics';

/**
 * Pomocník (plan §10.10): the articles grouped by role. Everyone may read every article
 * (decision 68); the index shows the customer articles to all, the staff ones to staff and
 * admins, the admin ones to admins.
 */

function shownTo(me: Me | null | undefined, group: HelpGroup): boolean {
  if (group === 'customer') return true;
  if (!me) return false;
  if (group === 'staff') return seesProviderScreens(me);
  return onPlatform(me, 'platform.overview');
}

export function HelpPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const articles = allArticles();
  return (
    <Stack gap="lg" maw={960}>
      <Stack gap={4}>
        <Title order={1}>{t('help.title')}</Title>
        <Text c="dimmed">{t('help.intro')}</Text>
      </Stack>
      {HELP_GROUPS.filter((group) => shownTo(me, group)).map((group) => (
        <Stack key={group} gap="sm" component="section" aria-labelledby={`help-${group}`}>
          <Title order={2} id={`help-${group}`}>
            {t(`help.groups.${group}`)}
          </Title>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            {articles
              .filter((article) => article.group === group)
              .map((article) => (
                <Card key={article.id} withBorder padding="md">
                  <AnchorLink
                    to="/help/$articleId"
                    params={{ articleId: article.id }}
                    fw={600}
                    size="lg"
                  >
                    {article.title}
                  </AnchorLink>
                  <Text size="sm" c="dimmed" mt={4}>
                    {article.lead}
                  </Text>
                </Card>
              ))}
          </SimpleGrid>
        </Stack>
      ))}
    </Stack>
  );
}
