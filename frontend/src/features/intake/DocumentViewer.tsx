import {
  ActionIcon,
  Box,
  Group,
  Paper,
  SegmentedControl,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import { IconArrowsMaximize, IconZoomIn, IconZoomOut } from '@tabler/icons-react';
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { pageUrl } from './api';

/** A box to show on the document: left, top, right, bottom in the page image's pixels. */
export interface Highlight {
  page: number;
  box: number[];
}

const ZOOMS = [1, 1.5, 2, 3, 4] as const;

/**
 * The document viewer of the check step (plan §8.5, §10.4): the pages as they were read,
 * zoomed with the buttons or + and −, panned by dragging (or scrolling, or the arrow keys
 * once focused), and the box of the focused field highlighted and scrolled into view, its
 * page shown.
 */
export function DocumentViewer({
  customerId,
  documentId,
  pages,
  highlight,
}: {
  customerId: string;
  documentId: string;
  pages: number;
  highlight: Highlight | null;
}) {
  const { t } = useTranslation();
  const [page, setPage] = useState(0);
  const [zoom, setZoom] = useState(0);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const marker = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);

  // A field on another page brings its page (state adjusted while rendering, as React
  // advises for state that follows a prop).
  const wanted = highlight?.page;
  const [followed, setFollowed] = useState(wanted);
  if (wanted !== followed) {
    setFollowed(wanted);
    if (wanted !== undefined && wanted < pages) setPage(wanted);
  }

  // The box scrolled into the middle of the viewer (only the viewer scrolls, never the page).
  const key = highlight ? `${String(highlight.page)}:${highlight.box.join(',')}` : '';
  useEffect(() => {
    const view = scroller.current;
    const box = marker.current;
    if (!view || !box) return;
    view.scrollTop = Math.max(0, box.offsetTop - view.clientHeight / 3);
    view.scrollLeft = Math.max(0, box.offsetLeft - view.clientWidth / 4);
  }, [key, page, zoom, size]);

  const step = (by: number) => {
    setZoom((z) => Math.min(ZOOMS.length - 1, Math.max(0, z + by)));
  };

  const keys = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === '+' || event.key === '=') {
      event.preventDefault();
      step(1);
    } else if (event.key === '-') {
      event.preventDefault();
      step(-1);
    }
  };

  // Dragging with the mouse pans; touch pans the scroll area natively.
  const down = (event: PointerEvent<HTMLDivElement>) => {
    const view = scroller.current;
    if (event.pointerType !== 'mouse' || event.button !== 0 || !view) return;
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      left: view.scrollLeft,
      top: view.scrollTop,
    };
    view.setPointerCapture(event.pointerId);
  };
  const move = (event: PointerEvent<HTMLDivElement>) => {
    const view = scroller.current;
    const from = drag.current;
    if (!view || !from) return;
    view.scrollLeft = from.left - (event.clientX - from.x);
    view.scrollTop = from.top - (event.clientY - from.y);
  };
  const up = (event: PointerEvent<HTMLDivElement>) => {
    drag.current = null;
    if (scroller.current?.hasPointerCapture(event.pointerId)) {
      scroller.current.releasePointerCapture(event.pointerId);
    }
  };

  const shown = highlight?.page === page && size ? highlight.box : null;
  const percent = (value: number, of: number) => `${String((value / of) * 100)}%`;
  const factor = ZOOMS[zoom] ?? 1;

  return (
    <Paper withBorder radius="md" p="xs" role="region" aria-label={t('viewer.label')}>
      <Stack gap="xs">
        <Group justify="space-between" gap="xs">
          {pages > 1 ? (
            <SegmentedControl
              size="xs"
              aria-label={t('viewer.pages')}
              value={String(page)}
              onChange={(value) => {
                setPage(Number(value));
              }}
              data={Array.from({ length: pages }, (_, i) => ({
                value: String(i),
                label: t('viewer.pageShort', { n: i + 1 }),
              }))}
            />
          ) : (
            <Text size="sm" c="dimmed">
              {t('viewer.single')}
            </Text>
          )}
          <Group gap={4}>
            <Tooltip label={t('viewer.zoomOut')}>
              <ActionIcon
                variant="default"
                aria-label={t('viewer.zoomOut')}
                disabled={zoom === 0}
                onClick={() => {
                  step(-1);
                }}
              >
                <IconZoomOut size={16} aria-hidden />
              </ActionIcon>
            </Tooltip>
            <Text size="sm" w={48} ta="center" aria-live="polite">
              {`${String(Math.round(factor * 100))} %`}
            </Text>
            <Tooltip label={t('viewer.zoomIn')}>
              <ActionIcon
                variant="default"
                aria-label={t('viewer.zoomIn')}
                disabled={zoom === ZOOMS.length - 1}
                onClick={() => {
                  step(1);
                }}
              >
                <IconZoomIn size={16} aria-hidden />
              </ActionIcon>
            </Tooltip>
            <Tooltip label={t('viewer.fit')}>
              <ActionIcon
                variant="default"
                aria-label={t('viewer.fit')}
                disabled={zoom === 0}
                onClick={() => {
                  setZoom(0);
                }}
              >
                <IconArrowsMaximize size={16} aria-hidden />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
        {/* A labelled region that takes the focus, so it pans with the arrow keys (WCAG
            2.1.1; axe: scrollable-region-focusable), as ScrollTable's box does. */}
        <Box
          ref={scroller}
          tabIndex={0}
          role="region"
          aria-label={t('viewer.page', { n: page + 1 })}
          aria-describedby="viewer-help"
          onKeyDown={keys}
          onPointerDown={down}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={up}
          style={{
            overflow: 'auto',
            maxHeight: 'min(75vh, 1100px)',
            cursor: zoom > 0 ? 'grab' : undefined,
            background: 'var(--mantine-color-default-hover)',
            touchAction: 'pan-x pan-y',
          }}
        >
          <div style={{ position: 'relative', width: `${String(factor * 100)}%` }}>
            <img
              key={page}
              src={pageUrl(customerId, documentId, page)}
              alt={t('viewer.image', { n: page + 1 })}
              draggable={false}
              style={{ display: 'block', width: '100%', height: 'auto', userSelect: 'none' }}
              onLoad={(event) => {
                const image = event.currentTarget;
                setSize({ width: image.naturalWidth, height: image.naturalHeight });
              }}
            />
            {shown && size && (
              <div
                ref={marker}
                data-testid="viewer-highlight"
                aria-hidden
                style={{
                  position: 'absolute',
                  left: percent(shown[0] ?? 0, size.width),
                  top: percent(shown[1] ?? 0, size.height),
                  width: percent((shown[2] ?? 0) - (shown[0] ?? 0), size.width),
                  height: percent((shown[3] ?? 0) - (shown[1] ?? 0), size.height),
                  outline: '3px solid var(--mantine-color-orange-6)',
                  outlineOffset: 2,
                  background: 'color-mix(in srgb, var(--mantine-color-yellow-4) 30%, transparent)',
                  borderRadius: 2,
                  pointerEvents: 'none',
                }}
              />
            )}
          </div>
        </Box>
        <Text id="viewer-help" size="xs" c="dimmed">
          {t('viewer.help')}
        </Text>
      </Stack>
    </Paper>
  );
}
