const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');

async function main() {
  if (process.platform !== 'win32') throw new Error('The packaged backend smoke check requires Windows.');
  const key = process.env.RUBY_SMOKE_GEMINI_KEY;
  if (!key) throw new Error('Set the non-secret RUBY_SMOKE_GEMINI_KEY test value.');
  const root = path.resolve('release', 'win-unpacked');
  const executable = path.join(root, 'resources', 'backend', 'ruby-backend.exe');
  if (!fs.existsSync(executable)) throw new Error('The packaged backend executable is missing from win-unpacked.');

  const nonce = crypto.randomUUID();
  const shutdownFile = path.join(os.tmpdir(), `ruby-backend-smoke-${nonce}.stop`);
  const workspace = path.join(os.tmpdir(), `ruby-backend-smoke-${nonce}`);
  const token = crypto.randomBytes(32).toString('base64url');
  const systemRoot = process.env.SystemRoot || 'C:\\Windows';
  const childEnv = {
    SystemRoot: systemRoot,
    WINDIR: process.env.WINDIR || systemRoot,
    LOCALAPPDATA: process.env.LOCALAPPDATA,
    TEMP: process.env.TEMP || os.tmpdir(),
    TMP: process.env.TMP || os.tmpdir(),
    PATH: [path.join(systemRoot, 'System32'), systemRoot].join(path.delimiter),
    GEMINI_API_KEY: key,
    RUBY_BRIDGE_TOKEN: token,
  };
  const child = spawn(executable, [
    '--managed', '--host', '127.0.0.1', '--port', '0', '--shutdown-file', shutdownFile,
    '--workspace', workspace,
  ], { cwd: path.dirname(executable), env: childEnv, windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] });

  const exited = new Promise((resolve) => child.once('exit', (code) => resolve(code)));
  try {
    const baseUrl = await new Promise((resolve, reject) => {
      let buffer = '';
      const timeout = setTimeout(() => { child.kill(); reject(new Error('Packaged bridge readiness timed out.')); }, 30000);
      child.once('error', () => { clearTimeout(timeout); reject(new Error('Could not launch the packaged backend.')); });
      child.once('exit', (code) => { clearTimeout(timeout); reject(new Error(`Packaged backend exited before readiness (${code ?? 'unknown'}).`)); });
      child.stdout.on('data', async (chunk) => {
        buffer += chunk.toString();
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() || '';
        for (const line of lines) {
          const match = line.match(/^RUBY_BRIDGE_READY=(http:\/\/127\.0\.0\.1:\d+)$/);
          if (!match) continue;
          try {
            const response = await fetch(`${match[1]}/v1/health`, { signal: AbortSignal.timeout(3000) });
            if (response.ok) { clearTimeout(timeout); resolve(match[1]); }
          } catch { /* poll until startup deadline */ }
        }
      });
    });
    const response = await fetch(`${baseUrl}/v1/state`, {
      headers: { authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error('Packaged bridge rejected the host credential.');
    const state = await response.json();
    if (state.backend?.name !== 'local-tools') throw new Error('Packaged filesystem backend did not initialize.');
    process.stdout.write('Packaged Python runtime, loopback readiness, and bridge authentication: PASS\n');
  } finally {
    try { fs.writeFileSync(shutdownFile, 'stop'); } catch {}
    const code = await Promise.race([exited, new Promise((resolve) => setTimeout(() => resolve(null), 5000))]);
    if (code === null && child.exitCode === null) child.kill();
    try { fs.rmSync(shutdownFile, { force: true }); } catch {}
    try { fs.rmSync(workspace, { recursive: true, force: true }); } catch {}
  }
  if (child.exitCode !== null) process.stdout.write('Graceful packaged backend shutdown: PASS\n');
  else throw new Error('Packaged backend did not stop cleanly.');
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
