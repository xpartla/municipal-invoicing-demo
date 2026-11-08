import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';

/** The admin's outbox viewer (plan §5.3, §10.9). */

export type OutboxItem = Schemas['OutboxItemOut'];

export function useOutbox(page: number, size: number, to: string) {
  return useQuery({
    queryKey: ['outbox', page, size, to],
    queryFn: () =>
      unwrap(
        api.GET('/api/admin/outbox', { params: { query: { page, size, to: to || undefined } } }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useOutboxMessage(messageId: string | undefined) {
  return useQuery({
    queryKey: ['outbox', 'message', messageId],
    queryFn: () =>
      unwrap(
        api.GET('/api/admin/outbox/{message_id}', {
          params: { path: { message_id: messageId ?? '' } },
        }),
      ),
    enabled: messageId !== undefined,
  });
}
