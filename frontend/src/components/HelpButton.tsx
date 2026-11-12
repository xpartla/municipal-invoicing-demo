import { ActionIcon, Center, Drawer, Loader } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconQuestionMark } from '@tabler/icons-react';
import { useRouterState } from '@tanstack/react-router';
import { lazy, Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { topicFor, type ArticleId } from '../help/topics';

/** The panel, with the articles and the Markdown renderer, loads the first time it opens. */
const HelpPanel = lazy(() => import('../help/HelpPanel').then((m) => ({ default: m.HelpPanel })));

/** The article of the screen being shown: the route's, unless the screen names one. */
function useRouteTopic(): ArticleId | undefined {
  return useRouterState({
    select: (state) => {
      const match = state.matches.at(-1);
      return match ? topicFor(match.fullPath, match.search as Record<string, unknown>) : undefined;
    },
  });
}

/**
 * The contextual "?" of plan §10.10: it opens the screen's article in a side panel. Every
 * signed-in route has one (a test walks the route tree); a screen whose article depends on
 * its state names it through `useHelpTopic`.
 */
export function HelpButton({ pageTopic }: { pageTopic: ArticleId | undefined }) {
  const { t } = useTranslation();
  const routeTopic = useRouteTopic();
  const topic = pageTopic ?? routeTopic ?? 'zaciname';
  const [opened, { open, close }] = useDisclosure(false);
  const [shown, setShown] = useState<ArticleId>(topic);
  return (
    <>
      <ActionIcon
        variant="default"
        size="lg"
        aria-label={t('help.button')}
        title={t('help.button')}
        aria-haspopup="dialog"
        onClick={() => {
          setShown(topic);
          open();
        }}
      >
        <IconQuestionMark size={18} aria-hidden />
      </ActionIcon>
      <Drawer
        opened={opened}
        onClose={close}
        position="right"
        size="lg"
        title={t('help.panelTitle')}
        closeButtonProps={{ 'aria-label': t('common.close') }}
      >
        <Suspense
          fallback={
            <Center py="xl">
              <Loader size="sm" aria-label={t('common.loading')} />
            </Center>
          }
        >
          <HelpPanel articleId={shown} onArticle={setShown} onClose={close} />
        </Suspense>
      </Drawer>
    </>
  );
}
