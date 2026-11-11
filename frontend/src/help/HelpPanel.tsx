import { Anchor, Divider, Group, Stack, Title } from '@mantine/core';
import { useCallback, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { AnchorLink } from '../components/RouterLinks';
import { getArticle } from './articles';
import { HelpMarkdown } from './HelpMarkdown';
import type { ArticleId } from './topics';

/**
 * The side panel's content: the article a screen's "?" opened. A link to another article
 * opens it in the panel (a middle click still opens its page in a new tab); the footer
 * leads to the article's page and to Pomocník.
 */
export function HelpPanel({
  articleId,
  onArticle,
  onClose,
}: {
  articleId: ArticleId;
  onArticle: (id: ArticleId) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const article = getArticle(articleId);
  const panelLink = useCallback(
    (id: ArticleId, children: ReactNode) => (
      <Anchor
        href={`/help/${id}`}
        underline="always"
        onClick={(event) => {
          if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
          event.preventDefault();
          onArticle(id);
        }}
      >
        {children}
      </Anchor>
    ),
    [onArticle],
  );
  return (
    <Stack gap={0} component="article" aria-labelledby="help-panel-article">
      <Title order={3} id="help-panel-article" mb="sm">
        {article.title}
      </Title>
      <HelpMarkdown markdown={article.body} headingOffset={2} articleLink={panelLink} />
      <Divider my="md" />
      <Group gap="lg">
        <AnchorLink to="/help/$articleId" params={{ articleId }} onClick={onClose}>
          {t('help.openPage')}
        </AnchorLink>
        <AnchorLink to="/help" onClick={onClose}>
          {t('help.all')}
        </AnchorLink>
      </Group>
    </Stack>
  );
}
