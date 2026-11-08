import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Starts the backend for the E2E run: a temporary RISO_VAR_DIR, `riso migrate` (and
 * `riso seed` once P2-M1 adds it), then `riso serve` on a free port serving the built SPA.
 * The URL goes to the tests through RISO_E2E_URL. The returned function tears it all down.
 */

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const spaIndex = join(repoRoot, 'riso', 'web', 'dist', 'index.html');

function freePort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close(() => {
        if (address && typeof address === 'object') resolvePort(address.port);
        else reject(new Error('no port'));
      });
    });
  });
}

function riso(args: string[], env: NodeJS.ProcessEnv): void {
  const result = spawnSync('uv', ['run', 'riso', ...args], { cwd: repoRoot, env, stdio: 'pipe' });
  if (result.status !== 0) {
    throw new Error(`riso ${args.join(' ')} failed:\n${result.stderr.toString()}`);
  }
}

async function waitUntilUp(url: string, server: ChildProcess, log: () => string): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`riso serve exited with ${String(server.exitCode)}:\n${log()}`);
    }
    try {
      const response = await fetch(`${url}/api/entities`);
      if (response.ok) return;
    } catch {
      // not listening yet
    }
    await new Promise((wait) => setTimeout(wait, 250));
  }
  throw new Error(`riso serve did not answer at ${url} within 60 s:\n${log()}`);
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  if (!existsSync(spaIndex)) {
    throw new Error(`No built SPA at ${spaIndex}. Run \`pnpm build\` first.`);
  }
  const varDir = mkdtempSync(join(tmpdir(), 'riso-playwright-'));
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    RISO_VAR_DIR: varDir,
    RISO_ENV: 'test',
  };
  delete env.RISO_DB_URL;
  riso(['migrate'], env);

  const port = await freePort();
  const url = `http://127.0.0.1:${String(port)}`;
  let output = '';
  // Its own process group, so the teardown stops uv and the server it started together.
  const server = spawn('uv', ['run', 'riso', 'serve', '--port', String(port)], {
    cwd: repoRoot,
    env,
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.stdout.on('data', (chunk: Buffer) => (output += chunk.toString()));
  server.stderr.on('data', (chunk: Buffer) => (output += chunk.toString()));

  const stop = async () => {
    if (server.pid !== undefined && server.exitCode === null) {
      process.kill(-server.pid, 'SIGTERM');
      await new Promise((done) => server.once('exit', done));
    }
    rmSync(varDir, { recursive: true, force: true });
  };

  try {
    await waitUntilUp(url, server, () => output);
  } catch (error) {
    await stop();
    throw error;
  }
  process.env.RISO_E2E_URL = url;
  return stop;
}
