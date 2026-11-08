import { useRouterState } from '@tanstack/react-router';

/** The token of a link from a mail: it travels in the fragment (`/invitation#<token>`), which
 * never reaches the server. */
export function useLinkToken(): string {
  return useRouterState({ select: (state) => state.location.hash.replace(/^#/, '') });
}
