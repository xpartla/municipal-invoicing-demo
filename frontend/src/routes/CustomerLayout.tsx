import { Outlet, useParams } from '@tanstack/react-router';

import { useMe } from '../features/identity/api';
import { canOpenCustomer } from '../features/identity/capabilities';
import { NotFoundPage } from './NotFoundPage';

/** /c/$customerId/…: a customer the caller cannot open is "not found", inside the shell, as
 * the API answers 404 for it. */
export function CustomerLayout() {
  const { customerId } = useParams({ from: '/_app/c/$customerId' });
  const { data: me } = useMe();
  return me && canOpenCustomer(me, customerId) ? <Outlet /> : <NotFoundPage />;
}
