import { Box } from '@mantine/core';

/**
 * A table that scrolls sideways on narrow screens. The scrolling box is a labelled region
 * that takes the keyboard focus, so it can be scrolled without a mouse (WCAG 2.1.1; axe:
 * scrollable-region-focusable).
 */
export function ScrollTable({
  label,
  minWidth,
  children,
}: {
  label: string;
  minWidth: number;
  children: React.ReactNode;
}) {
  return (
    <Box
      role="region"
      aria-label={label}
      tabIndex={0}
      // Relative, so absolutely placed content (a visually hidden header) scrolls with the
      // table instead of widening the page.
      style={{ overflowX: 'auto', position: 'relative' }}
    >
      <Box miw={minWidth}>{children}</Box>
    </Box>
  );
}
