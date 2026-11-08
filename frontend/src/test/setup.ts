import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// jsdom lacks what Mantine measures with; these are the stubs Mantine's docs recommend.
const originalGetComputedStyle = window.getComputedStyle.bind(window);
window.getComputedStyle = (element) => originalGetComputedStyle(element);
window.HTMLElement.prototype.scrollIntoView = () => undefined;

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

class ResizeObserver {
  observe() {
    return undefined;
  }
  unobserve() {
    return undefined;
  }
  disconnect() {
    return undefined;
  }
}
window.ResizeObserver = ResizeObserver;

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
