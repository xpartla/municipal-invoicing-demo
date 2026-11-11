import { createContext, useContext, useEffect } from 'react';

import type { ArticleId } from './topics';

/**
 * A screen whose article depends on more than its route (the invoice page's tab follows the
 * invoice's state) names it here; the shell's "?" prefers it to the route's.
 */
export const HelpTopicContext = createContext<(topic: ArticleId | undefined) => void>(
  () => undefined,
);

export function useHelpTopic(topic: ArticleId | undefined): void {
  const set = useContext(HelpTopicContext);
  useEffect(() => {
    set(topic);
    return () => {
      set(undefined);
    };
  }, [set, topic]);
}
