import { Anchor, Blockquote, Code, Divider, List, Table, Text, Title } from '@mantine/core';
import { useMemo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { ScrollTable } from '../components/ScrollTable';
import { isArticleId, type ArticleId } from './topics';

/**
 * An article's Markdown as Mantine elements. react-markdown builds React elements and leaves
 * raw HTML out, so nothing is injected (plan §12: the strict CSP). A link whose target is an
 * article ID (`[Kontrola údajov](kontrola-udajov)`) goes through `articleLink`; web links open
 * in a new tab. `headingOffset` moves the headings down a level inside the side panel, whose
 * own title is the article's.
 */

type Level = 1 | 2 | 3 | 4 | 5 | 6;

function level(base: number, offset: number): Level {
  return Math.min(6, base + offset) as Level;
}

const WEB = /^(https?:|mailto:)/;

export function HelpMarkdown({
  markdown,
  headingOffset = 0,
  articleLink,
}: {
  markdown: string;
  headingOffset?: number;
  articleLink: (id: ArticleId, children: ReactNode) => ReactNode;
}) {
  const { t } = useTranslation();
  const components = useMemo(
    () => markdownComponents(headingOffset, articleLink, t('help.table')),
    [headingOffset, articleLink, t],
  );
  return (
    <Markdown remarkPlugins={[remarkGfm]} components={components}>
      {markdown}
    </Markdown>
  );
}

function markdownComponents(
  headingOffset: number,
  articleLink: (id: ArticleId, children: ReactNode) => ReactNode,
  tableLabel: string,
): Components {
  const heading = (base: number) =>
    function Heading({ children }: { children?: ReactNode }) {
      return (
        <Title order={level(base, headingOffset)} mt="lg" mb="xs">
          {children}
        </Title>
      );
    };
  return {
    h1: heading(1),
    h2: heading(2),
    h3: heading(3),
    h4: heading(4),
    p: ({ children }) => <Text mb="sm">{children}</Text>,
    ul: ({ children }) => (
      <List mb="sm" spacing={4} withPadding>
        {children}
      </List>
    ),
    ol: ({ children }) => (
      <List type="ordered" mb="sm" spacing={4} withPadding>
        {children}
      </List>
    ),
    li: ({ children }) => <List.Item>{children}</List.Item>,
    a: ({ href, children }) => {
      if (href && isArticleId(href)) return articleLink(href, children);
      if (href && WEB.test(href)) {
        return (
          <Anchor href={href} target="_blank" rel="noreferrer" underline="always">
            {children}
          </Anchor>
        );
      }
      return <>{children}</>;
    },
    code: ({ children }) => <Code>{children}</Code>,
    blockquote: ({ children }) => (
      <Blockquote color="blue" my="md" p="md">
        {children}
      </Blockquote>
    ),
    hr: () => <Divider my="lg" />,
    img: ({ alt }) => <>{alt}</>,
    table: ({ children }) => (
      <ScrollTable label={tableLabel} minWidth={480}>
        <Table mb="md" withTableBorder withColumnBorders>
          {children}
        </Table>
      </ScrollTable>
    ),
    thead: ({ children }) => <Table.Thead>{children}</Table.Thead>,
    tbody: ({ children }) => <Table.Tbody>{children}</Table.Tbody>,
    tr: ({ children }) => <Table.Tr>{children}</Table.Tr>,
    th: ({ children }) => <Table.Th>{children}</Table.Th>,
    td: ({ children }) => <Table.Td>{children}</Table.Td>,
  };
}
