import {
  Badge,
  createTheme,
  localStorageColorSchemeManager,
  type CSSVariablesResolver,
  type MantineColorsTuple,
} from '@mantine/core';

/**
 * Design tokens. Components take colours, spacing and sizes from here or from Mantine's
 * theme, never ad hoc (guide §6.7).
 */
export const tokens = {
  navbarWidth: 240,
  headerHeight: 56,
  contentMaxWidth: 1280,
} as const;

const riso: MantineColorsTuple = [
  '#e8f2ff',
  '#d0e2fb',
  '#a1c3f2',
  '#6ea2ea',
  '#4486e3',
  '#2a74df',
  '#1a6bde',
  '#0b5ac6',
  '#0050b2',
  '#00449e',
];

export const theme = createTheme({
  primaryColor: 'riso',
  colors: { riso },
  primaryShade: { light: 7, dark: 5 },
  // The system font stack: no web fonts to load, and the CSP allows only our own origin.
  fontFamily:
    'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif',
  headings: { fontWeight: '650' },
  defaultRadius: 'md',
  cursorType: 'pointer',
  // Text on filled colours turns black or white by the background's luminance, so badges and
  // buttons in every colour meet WCAG AA contrast (axe checks them).
  autoContrast: true,
  components: {
    Badge: Badge.extend({ defaultProps: { variant: 'filled' } }),
  },
});

/**
 * Our own CSS variables, per colour scheme, and two of Mantine's raised to WCAG AA contrast
 * (4.5:1 on the body background): dimmed text and links. axe checks them in the E2E specs.
 */
export const cssVariablesResolver: CSSVariablesResolver = (current) => ({
  variables: {
    '--riso-navbar-width': `${String(tokens.navbarWidth)}px`,
  },
  light: {
    '--riso-surface': current.white,
    '--riso-canvas': current.colors.gray[0],
    '--riso-border': current.colors.gray[3],
    '--mantine-color-dimmed': current.colors.gray[7],
    '--mantine-color-anchor': riso[7],
  },
  dark: {
    '--riso-surface': current.colors.dark[7],
    '--riso-canvas': current.colors.dark[8],
    '--riso-border': current.colors.dark[4],
    '--mantine-color-dimmed': current.colors.dark[1],
    '--mantine-color-anchor': riso[3],
  },
});

/** The same storage key public/color-scheme.js reads before the app loads. */
export const colorSchemeManager = localStorageColorSchemeManager({
  key: 'mantine-color-scheme-value',
});
