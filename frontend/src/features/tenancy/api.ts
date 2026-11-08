import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';
import { meKey } from '../identity/api';

/** Customers, providers and the user screens' lists (plan §5.5, §10.8–10.9). */

export type Customer = Schemas['CustomerOut'];
export type CustomerWithLogins = Schemas['CustomerWithLoginsOut'];
export type Login = Schemas['LoginOut'];
export type ProviderDetail = Schemas['ProviderDetailOut'];

export function useCustomer(customerId: string | undefined) {
  return useQuery({
    queryKey: ['customer', customerId],
    queryFn: () =>
      unwrap(
        api.GET('/api/customers/{customer_id}', {
          params: { path: { customer_id: customerId ?? '' } },
        }),
      ),
    enabled: customerId !== undefined,
  });
}

function useCustomerMutation<T>(call: (customerId: string, body: T) => Promise<Customer>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ customerId, body }: { customerId: string; body: T }) => call(customerId, body),
    onSuccess: async (customer) => {
      client.setQueryData(['customer', customer.id], customer);
      await client.invalidateQueries({ queryKey: ['directory'] });
      await client.invalidateQueries({ queryKey: meKey });
    },
  });
}

const path = (customerId: string) => ({ path: { customer_id: customerId } });

export function useUpdateContact() {
  return useCustomerMutation((customerId, body: Schemas['CustomerContactIn']) =>
    unwrap(api.PATCH('/api/customers/{customer_id}/contact', { params: path(customerId), body })),
  );
}

export function useUpdateIdentity() {
  return useCustomerMutation((customerId, body: Schemas['CustomerIdentityIn']) =>
    unwrap(api.PATCH('/api/customers/{customer_id}/identity', { params: path(customerId), body })),
  );
}

export function useAssignVariableNumber() {
  return useCustomerMutation((customerId, body: Schemas['VariableNumberIn']) =>
    unwrap(
      api.PUT('/api/customers/{customer_id}/variable-number', { params: path(customerId), body }),
    ),
  );
}

/** A provider's customers with their logins (staff), or every customer (admins). */
export function useDirectory(scope: { providerId: string } | 'all' | undefined) {
  return useQuery({
    queryKey: ['directory', scope],
    queryFn: () =>
      scope === 'all'
        ? unwrap(api.GET('/api/admin/customers'))
        : unwrap(
            api.GET('/api/providers/{provider_id}/customers', {
              params: { path: { provider_id: scope?.providerId ?? '' } },
            }),
          ),
    enabled: scope !== undefined,
  });
}

// Providers (admins) ----------------------------------------------------------------------

export const providersKey = ['providers'] as const;

export function useProviders() {
  return useQuery({
    queryKey: providersKey,
    queryFn: () => unwrap(api.GET('/api/admin/providers')),
  });
}

function useProviderMutation<T>(call: (args: T) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: call,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: providersKey });
      await client.invalidateQueries({ queryKey: ['directory'] });
    },
  });
}

export function useCreateProvider() {
  return useProviderMutation((body: Schemas['ProviderIn']) =>
    unwrap(api.POST('/api/admin/providers', { body })),
  );
}

export function useRemoveProvider() {
  return useProviderMutation((providerId: string) =>
    unwrap(
      api.DELETE('/api/admin/providers/{provider_id}', {
        params: { path: { provider_id: providerId } },
      }),
    ),
  );
}

export function useAddStaff() {
  return useProviderMutation(
    ({ providerId, body }: { providerId: string; body: Schemas['StaffIn'] }) =>
      unwrap(
        api.POST('/api/admin/providers/{provider_id}/staff', {
          params: { path: { provider_id: providerId } },
          body,
        }),
      ),
  );
}

export function useRemoveStaff() {
  return useProviderMutation(({ providerId, userId }: { providerId: string; userId: string }) =>
    unwrap(
      api.DELETE('/api/admin/providers/{provider_id}/staff/{user_id}', {
        params: { path: { provider_id: providerId, user_id: userId } },
      }),
    ),
  );
}

export function useAssignProvider() {
  return useProviderMutation(
    ({ customerId, providerId }: { customerId: string; providerId: string }) =>
      unwrap(
        api.PUT('/api/admin/customers/{customer_id}/provider', {
          params: path(customerId),
          body: { provider_id: providerId },
        }),
      ),
  );
}

export function useUnassignProvider() {
  return useProviderMutation((customerId: string) =>
    unwrap(api.DELETE('/api/admin/customers/{customer_id}/provider', { params: path(customerId) })),
  );
}
