const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { PassThrough } = require('node:stream');
const test = require('node:test');
const { BackendSupervisor } = require('./backend-supervisor.cjs');
const temporaryRoots = [];

test.after(() => temporaryRoots.forEach((root) => fs.rmSync(root, { recursive: true, force: true })));

function setup(overrides = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ruby-runtime-test-'));
  temporaryRoots.push(root);
  const app = { isPackaged: false, getPath: (name) => root };
  const safeStorage = {
    isEncryptionAvailable: () => true,
    encryptString: (value) => Buffer.from([...value].reverse().join('')),
    decryptString: (value) => [...value.toString()].reverse().join(''),
  };
  const states = [];
  const supervisor = new BackendSupervisor({ app, safeStorage, onState: (state) => states.push(state),
    env: { PATH: 'test-path' }, projectRoot: root, ...overrides });
  return { root, supervisor, states };
}

test('missing key requests first-run configuration without launching Python', async () => {
  let spawned = false;
  const { supervisor, states } = setup({ spawnProcess: () => { spawned = true; } });
  await supervisor.start();
  assert.equal(supervisor.state.status, 'CONFIGURATION_REQUIRED');
  assert.equal(spawned, false);
  assert.ok(states.some((state) => state.status === 'CONFIGURATION_REQUIRED'));
});

test('development selects production launcher and supplies secrets only to child environment', () => {
  const { supervisor } = setup({ env: { PATH: 'test-path', RUBY_PYTHON_EXECUTABLE: 'python-test' } });
  assert.deepEqual(supervisor.backendCommand().prefix, ['-m', 'background_agent.bridge.production_server']);
  const env = supervisor.childEnv('key-for-test', 'token-for-test');
  assert.equal(env.GEMINI_API_KEY, 'key-for-test');
  assert.equal(env.RUBY_BRIDGE_TOKEN, 'token-for-test');
});

test('packaged mode fails clearly when bundled runtime is absent', () => {
  const { supervisor } = setup({ app: { isPackaged: true, getPath: () => os.tmpdir() }, resourcesPath: 'C:/Ruby/resources' });
  assert.throws(() => supervisor.backendCommand(), /bundled assistant runtime is missing/);
});

test('readiness waits for the loopback health endpoint', async () => {
  let child;
  const { supervisor } = setup({
    spawnProcess: () => {
      child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
      child.exitCode = null; child.kill = () => { child.killed = true; };
      return child;
    },
    fetchImpl: async (url) => ({ ok: url === 'http://127.0.0.1:43210/v1/health' }),
  });
  const starting = supervisor.startWithKey('test-key');
  child.stdout.write('RUBY_BRIDGE_READY=http://127.0.0.1:43210\n');
  await starting;
  assert.equal(supervisor.state.status, 'READY');
  assert.equal(supervisor.baseUrl, 'http://127.0.0.1:43210');
});

test('backend startup failures become an actionable runtime error', async () => {
  const { supervisor } = setup({ spawnProcess: () => { throw new Error('private provider detail'); } });
  await supervisor.startWithKey('test-key');
  assert.equal(supervisor.state.status, 'BACKEND_ERROR');
  assert.match(supervisor.state.error, /runtime/);
  assert.doesNotMatch(JSON.stringify(supervisor.state), /private provider detail/);
});

test('backend exiting before readiness produces a visible startup failure', async () => {
  const { supervisor } = setup({
    spawnProcess: () => {
      const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
      child.exitCode = null; child.kill = () => {};
      process.nextTick(() => { child.exitCode = 2; child.emit('exit', 2); });
      return child;
    },
  });
  await supervisor.startWithKey('test-key');
  assert.equal(supervisor.state.status, 'BACKEND_ERROR');
  assert.match(supervisor.state.error, /exited during startup/);
});

test('a backend crash triggers recovery and retries remain bounded', async () => {
  const { supervisor } = setup();
  let starts = 0;
  supervisor.startWithKey = async () => { starts += 1; };
  const crashed = new EventEmitter();
  supervisor.child = crashed;
  await supervisor.handleExit(crashed, 1, 'test-key');
  assert.equal(starts, 1);
  const finalCrash = new EventEmitter();
  supervisor.child = finalCrash;
  supervisor.restarts = 2;
  await supervisor.handleExit(finalCrash, 1, 'test-key');
  assert.equal(starts, 1);
  assert.equal(supervisor.state.status, 'BACKEND_ERROR');
});

test('a crashed backend restarts and the supervisor reconnects to the replacement bridge', async () => {
  const children = [];
  const { supervisor } = setup({
    spawnProcess: () => {
      const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
      child.exitCode = null; child.kill = () => { child.killed = true; };
      children.push(child);
      process.nextTick(() => child.stdout.write(`RUBY_BRIDGE_READY=http://127.0.0.1:${43000 + children.length}\n`));
      return child;
    },
    fetchImpl: async () => ({ ok: true }),
  });
  await supervisor.startWithKey('test-key');
  assert.equal(supervisor.baseUrl, 'http://127.0.0.1:43001');
  children[0].exitCode = 1;
  children[0].emit('exit', 1);
  const deadline = Date.now() + 2500;
  while (supervisor.state.status !== 'READY' || supervisor.baseUrl.endsWith(':43001')) {
    if (Date.now() > deadline) throw new Error('replacement bridge did not reconnect');
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.equal(supervisor.baseUrl, 'http://127.0.0.1:43002');
  setTimeout(() => { children[1].exitCode = 0; children[1].emit('exit', 0); }, 20);
  await supervisor.stop();
});

test('shutdown requests graceful exit and removes its temporary marker', async () => {
  const { supervisor } = setup();
  const child = new EventEmitter();
  child.exitCode = null;
  child.killed = false;
  child.kill = () => { child.killed = true; };
  supervisor.child = child;
  setTimeout(() => { child.exitCode = 0; child.emit('exit', 0); }, 20);
  await supervisor.stop();
  assert.equal(supervisor.child, null);
  assert.equal(fs.existsSync(supervisor.stopFile), false);
  assert.equal(child.killed, false);
});

test('API key storage uses encrypted data and decrypts only in the host process', () => {
  const { root, supervisor } = setup();
  supervisor.writeKey('sensitive-test-value');
  const stored = fs.readFileSync(path.join(root, 'gemini-key.bin'));
  assert.equal(stored.includes(Buffer.from('sensitive-test-value')), false);
  assert.equal(supervisor.readKey(), 'sensitive-test-value');
});


test('configuration validates before persisting and starts the managed backend', async () => {
  const children = [];
  const { root, supervisor } = setup({
    spawnProcess: (_command, args, options) => {
      const child = new EventEmitter();
      child.exitCode = null;
      child.kill = () => { child.killed = true; };
      if (args.includes('--validate-gemini')) {
        process.nextTick(() => { child.exitCode = 0; child.emit('exit', 0); });
      } else {
        child.stdout = new PassThrough(); child.stderr = new PassThrough();
        child.environmentForTest = options.env;
        process.nextTick(() => child.stdout.write('RUBY_BRIDGE_READY=http://127.0.0.1:43210\n'));
      }
      children.push(child);
      return child;
    },
    fetchImpl: async () => ({ ok: true }),
  });
  await supervisor.configureKey('test-gemini-key-which-is-long-enough');
  assert.equal(children.length, 2);
  assert.ok(children[1].environmentForTest.GEMINI_API_KEY);
  assert.ok(children[1].environmentForTest.RUBY_BRIDGE_TOKEN);
  assert.equal(supervisor.state.status, 'READY');
  assert.equal(fs.readFileSync(path.join(root, 'gemini-key.bin')).includes(Buffer.from('test-gemini-key-which-is-long-enough')), false);
});

test('a rejected replacement key does not replace the live bridge credential or saved key', async () => {
  const { root, supervisor } = setup({
    spawnProcess: () => {
      const child = new EventEmitter(); child.exitCode = null; child.kill = () => {};
      process.nextTick(() => { child.exitCode = 3; child.emit('exit', 3); });
      return child;
    },
  });
  supervisor.state = { status: 'READY', message: 'Ruby is ready.' };
  supervisor.token = 'existing-live-bridge-token';
  await assert.rejects(supervisor.configureKey('invalid-key-value-that-is-long-enough'), /could not validate/);
  assert.equal(supervisor.token, 'existing-live-bridge-token');
  assert.equal(fs.existsSync(path.join(root, 'gemini-key.bin')), false);
  assert.equal(supervisor.state.status, 'READY');
});

test('preload provides a clipboard setup action and no key retrieval path', () => {
  const preload = fs.readFileSync(path.join(__dirname, 'preload.cjs'), 'utf8');
  assert.match(preload, /configureGeminiFromClipboard/);
  assert.doesNotMatch(preload, /configureGeminiKey|GEMINI_API_KEY|RUBY_BRIDGE_TOKEN/);
});
