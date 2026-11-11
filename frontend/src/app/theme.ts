import {
  Alert,
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
  // Black text from this luminance up, white below. At 0.179 both meet 4.5:1: black needs a
  // background of L >= 0.175 ((L + 0.05) / 0.05), white one of L <= 0.183 (1.05 / (L + 0.05)).
  // Mantine's default (0.3) gave white text on blue.6 at 3.6:1.
  luminanceThreshold: 0.179,
  components: {
    // A light alert's title is drawn in its colour; yellow on the pale yellow background is
    // 1.9:1. The title takes the text colour; the border and the icon keep the alert's.
    Alert: Alert.extend({
      styles: { title: { color: 'var(--mantine-color-text)' } },
    }),
    Badge: Badge.extend({
      defaultProps: { variant: 'filled' },
      // A filled gray badge is gray.7 in light and gray.5 in dark, either side of the
      // threshold, but autoContrast picks one text colour for both: white, 2:1 on gray.5.
      // The text colour follows the scheme instead (--riso-on-gray).
      vars: (_theme, props) =>
        props.color === 'gray' && (props.variant ?? 'filled') === 'filled'
          ? { root: { '--badge-color': 'var(--riso-on-gray)' } }
          : { root: {} },
    }),
  },
});

/**
 * Our own CSS variables, per colour scheme, and three of Mantine's raised to WCAG AA contrast
 * (4.5:1 on the body background): dimmed text, links, and the error colour of a field's text
 * and message (Mantine's red.6 is 3.3:1 on white, its dark red.8 3.4:1 on dark.7; red.9 gives
 * 5.2:1 on gray.0, red.5 4.9:1 on an input's dark.6). axe checks them in the E2E specs.
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
    '--mantine-color-error': current.colors.red[9],
    '--riso-on-gray': current.white,
  },
  dark: {
    '--riso-surface': current.colors.dark[7],
    '--riso-canvas': current.colors.dark[8],
    '--riso-border': current.colors.dark[4],
    '--mantine-color-dimmed': current.colors.dark[1],
    '--mantine-color-anchor': riso[3],
    '--mantine-color-error': current.colors.red[5],
    '--riso-on-gray': current.black,
  },
});

/** The same storage key public/color-scheme.js reads before the app loads. */
export const colorSchemeManager = localStorageColorSchemeManager({
  key: 'mantine-color-scheme-value',
});
