import { createContext } from 'react';

/** True inside the shell, whose AppShell.Main is the page's `main` landmark. */
export const InShellContext = createContext(false);
