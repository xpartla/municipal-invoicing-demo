import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './app/App';
import { createQueryClient } from './app/queryClient';
import { createAppRouter } from './app/router';

const root = document.getElementById('root');
if (!root) throw new Error('index.html has no #root element');

const queryClient = createQueryClient();
createRoot(root).render(
  <StrictMode>
    <App router={createAppRouter(queryClient)} queryClient={queryClient} />
  </StrictMode>,
);
