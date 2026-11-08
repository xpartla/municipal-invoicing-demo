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

// The caller's own account ---------------------------------------------------------------

export type SessionInfo = Schemas['SessionOut'];

export function useSessions() {
  return useQuery({
    queryKey: ['me', 'sessions'],
    queryFn: () => unwrap(api.GET('/api/me/sessions')),
  });
}

export function useUpdateProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas['ProfileIn']) => unwrap(api.PATCH('/api/me', { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: meKey }),
  });
}

export function useChangePassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas['ChangePasswordIn']) =>
      unwrap(api.POST('/api/me/password', { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ['me', 'sessions'] }),
  });
}

export function useRequestEmailChange() {
  return useMutation({
    mutationFn: (body: Schemas['EmailChangeIn']) =>
      unwrap(api.POST('/api/me/email-change', { body })),
  });
}

export function useLogoutEverywhere() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/auth/logout-all')),
    onSettled: () => {
      client.clear();
      client.setQueryData(meKey, null);
    },
  });
}

// Every account (admins) and a customer's logins (staff, admins) --------------------------

export const usersKey = ['users'] as const;

export function useUsers(query: string, includeDeleted: boolean) {
  return useQuery({
    queryKey: [...usersKey, query, includeDeleted],
    queryFn: () =>
      unwrap(
        api.GET('/api/admin/users', {
          params: { query: { q: query || undefined, include_deleted: includeDeleted } },
        }),
      ),
  });
}

export type UserAction = 'lock' | 'unlock' | 'logout' | 'delete' | 'restore' | 'purge';

export function useUserAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, action }: { userId: string; action: UserAction }): Promise<unknown> => {
      const path = { params: { path: { user_id: userId } } };
      switch (action) {
        case 'lock':
          return unwrap(api.POST('/api/admin/users/{user_id}/lock', path));
        case 'unlock':
          return unwrap(api.POST('/api/admin/users/{user_id}/unlock', path));
        case 'logout':
          return unwrap(api.POST('/api/admin/users/{user_id}/logout', path));
        case 'delete':
          return unwrap(api.POST('/api/admin/users/{user_id}/delete', path));
        case 'restore':
          return unwrap(api.POST('/api/admin/users/{user_id}/restore', path));
        case 'purge':
          return unwrap(api.POST('/api/admin/users/{user_id}/purge', path));
      }
    },
    onSuccess: () => client.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useInviteLogin(customerId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas['InviteIn']) =>
      unwrap(
        api.POST('/api/customers/{customer_id}/logins', {
          params: { path: { customer_id: customerId } },
          body,
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ['directory'] }),
  });
}

export type LoginAction = 'deactivate' | 'reactivate' | 'reset-link';

export function useLoginAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      customerId,
      userId,
      action,
    }: {
      customerId: string;
      userId: string;
      action: LoginAction;
    }): Promise<unknown> => {
      const params = { params: { path: { customer_id: customerId, user_id: userId } } };
      switch (action) {
        case 'deactivate':
          return unwrap(
            api.POST('/api/customers/{customer_id}/logins/{user_id}/deactivate', params),
          );
        case 'reactivate':
          return unwrap(
            api.POST('/api/customers/{customer_id}/logins/{user_id}/reactivate', params),
          );
        case 'reset-link':
          return unwrap(
            api.POST('/api/customers/{customer_id}/logins/{user_id}/reset-link', params),
          );
      }
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ['directory'] }),
  });
}
