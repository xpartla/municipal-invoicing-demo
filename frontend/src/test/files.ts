import { File as NodeFile } from 'node:buffer';
import { expect, vi } from 'vitest';

/**
 * Files to upload in component tests. Under Vitest the client's Request is Node's and
 * FormData and File jsdom's, which do not mix (a file arrives as "blob"): `nodeForms` puts
 * Node's FormData in place and `nodeFile` makes Node's File, as a browser has one of each.
 */
export async function nodeForms(): Promise<void> {
  const form = await new Response('', {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  }).formData();
  const NodeFormData = form.constructor as new () => FormData;
  // Built from a form element (by the test tools, not by the app), it starts empty.
  class EmptyFormData extends NodeFormData {
    constructor(...ignored: unknown[]) {
      super();
      expect(ignored.length).toBeLessThanOrEqual(2);
    }
  }
  vi.stubGlobal('FormData', EmptyFormData);
}

export function nodeFile(name: string, type: string, content = 'data'): File {
  return new NodeFile([content], name, { type }) as unknown as File;
}
