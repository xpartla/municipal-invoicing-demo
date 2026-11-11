import { Stack, Text, Title } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { useParams } from '@tanstack/react-router';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { AnchorLink } from '../components/RouterLinks';
import { getArticle } from '../help/articles';
import { HelpMarkdown } from '../help/HelpMarkdown';
import { isArticleId, type ArticleId } from '../help/topics';

function pageLink(id: ArticleId, children: ReactNode) {
  return (
    <AnchorLink to="/help/$articleId" params={{ articleId: id }} underline="always">
      {children}
    </AnchorLink>
  );
}

/** One article of Pomocník, as a page. */
export function HelpArticlePage() {
  const { t } = useTranslation();
  const { articleId } = useParams({ from: '/_app/help/$articleId' });
  const back = (
    <AnchorLink to="/help" size="sm">
      <IconArrowLeft size={14} aria-hidden /> {t('help.back')}
    </AnchorLink>
  );
  if (!isArticleId(articleId)) {
    return (
      <Stack gap="sm" maw={760}>
        {back}
        <Title order={1}>{t('help.notFound')}</Title>
        <Text>{t('help.notFoundText')}</Text>
      </Stack>
    );
  }
  const article = getArticle(articleId);
  return (
    <Stack gap={0} maw={760} component="article">
      {back}
      <Title order={1} mt="xs" mb="sm">
        {article.title}
      </Title>
      <HelpMarkdown markdown={article.body} articleLink={pageLink} />
    </Stack>
  );
}
