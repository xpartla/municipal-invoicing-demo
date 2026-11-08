import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { ApiError, unwrap } from '../../lib/apiError';

/**
 * The identity API through TanStack Query (guide §6.7): the caller (`/api/me`), logging in
 * and out, and the pages reached from mail links.
 */

export type Me = Schemas['MeOut'];
export type UserInfo = Schemas['UserOut'];
export type TokenInfo = Schemas['TokenInfoOut'];

export const meKey = ['me'] as const;

/** The caller, or null when nobody is logged in (a 401). */
export const meQuery = queryOptions({
  queryKey: meKey,
  queryFn: async (): Promise<Me | null> => {
    try {
      return await unwrap(api.GET('/api/me'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },
  staleTime: 60_000,
});

export function useMe() {
  return useQuery(meQuery);
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      unwrap(api.POST('/api/auth/login', { body })),
    onSuccess: (me) => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== meKey[0] });
      client.setQueryData(meKey, me);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/auth/logout')),
    onSettled: () => {
      client.clear();
      client.setQueryData(meKey, null);
    },
  });
}

export function useEndImpersonation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/me/impersonation/end')),
    onSuccess: async () => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== meKey[0] });
      await client.invalidateQueries({ queryKey: meKey });
    },
  });
}

export function useStartImpersonation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, reason }: { userId: string; reason: string }) =>
      unwrap(
        api.POST('/api/admin/users/{user_id}/impersonate', {
          params: { path: { user_id: userId } },
          body: { reason },
        }),
      ),
    onSuccess: async () => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== meKey[0] });
      await client.invalidateQueries({ queryKey: meKey });
    },
  });
}

// Links from mail ---------------------------------------------------------------------------

export function useTokenInfo(token: string) {
  return useQuery({
    queryKey: ['token-info', token],
    queryFn: () => unwrap(api.POST('/api/auth/token-info', { body: { token } })),
    enabled: token !== '',
    retry: false,
    staleTime: Infinity,
  });
}

export function useAcceptInvitation() {
  return useMutation({
    mutationFn: (body: { token: string; password: string }) =>
      unwrap(api.POST('/api/auth/invitation/accept', { body })),
  });
}

export function useRequestReset() {
  return useMutation({
    mutationFn: (body: { email: string }) => unwrap(api.POST('/api/auth/password-reset', { body })),
  });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: (body: { token: string; password: string }) =>
      unwrap(api.POST('/api/auth/password-reset/complete', { body })),
  });
}

export function useConfirmEmailChange() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { token: string }) =>
      unwrap(api.POST('/api/auth/email-change/confirm', { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: meKey }),
  });
}
