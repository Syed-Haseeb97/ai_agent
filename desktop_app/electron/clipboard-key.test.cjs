const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const { registerClipboardKeyHandler } = require('./clipboard-key.cjs');

const channel = 'ruby:runtime:configure-key-from-clipboard';

function setup({ platform = 'win32', electronReads = [''], fallbackReads = ['test-gemini-key-value-123456'], configureKey = async () => true } = {}) {
  let handler;
  let clears = 0;
  let fallbackCalls = 0;
  const invocations = [];
  const ipcMain = { handle: (name, callback) => { assert.equal(name, channel); handler = callback; } };
  const clipboard = {
    readText: () => electronReads.shift() ?? '',
    clear: () => { clears += 1; },
  };
  const backend = { state: { status: 'READY' }, configureKey };
  registerClipboardKeyHandler({
    ipcMain,
    clipboard,
    getBackend: () => backend,
    platform,
    execFileImpl: (...args) => {
      invocations.push(args);
      const callback = args[3];
      callback(null, fallbackReads[fallbackCalls++] ?? '');
    },
  });
  return {
    invoke: () => handler(),
    get clears() { return clears; },
    invocations,
    get fallbackCalls() { return fallbackCalls; },
  };
}

test('uses Electron clipboard text first and clears it only after successful configuration', async () => {
  const clipboard = setup({
    platform: 'linux',
    electronReads: ['test-gemini-key-value-123456', 'test-gemini-key-value-123456'],
  });
  assert.deepEqual(await clipboard.invoke(), { status: 'READY' });
  assert.equal(clipboard.clears, 1);
  assert.equal(clipboard.fallbackCalls, 0);
});

test('uses bounded, hidden PowerShell fallback only when Electron returns empty', async () => {
  const clipboard = setup();
  await clipboard.invoke();
  assert.equal(clipboard.fallbackCalls, 2);
  const [command, args, options] = clipboard.invocations[0];
  assert.equal(command, 'powershell.exe');
  assert.deepEqual(args, ['-NoProfile', '-NonInteractive', '-Command', '[Console]::Write((Get-Clipboard -Raw))']);
  assert.deepEqual(options, {
    encoding: 'utf8',
    maxBuffer: 64 * 1024,
    timeout: 2000,
    windowsHide: true,
  });
  assert.equal(JSON.stringify(clipboard.invocations).includes('test-gemini-key-value-123456'), false);
});

test('does not clear a changed clipboard value', async () => {
  const clipboard = setup({ fallbackReads: ['test-gemini-key-value-123456', 'different-test-value-123456'] });
  await clipboard.invoke();
  assert.equal(clipboard.clears, 0);
});

test('does not clear clipboard when backend configuration fails', async () => {
  const clipboard = setup({
    configureKey: async () => { throw new Error('Gemini could not validate this key.'); },
  });
  await assert.rejects(clipboard.invoke(), /could not validate/);
  assert.equal(clipboard.clears, 0);
  assert.equal(clipboard.fallbackCalls, 1);
});

test('reports an empty clipboard without invoking backend configuration', async () => {
  const clipboard = setup({ fallbackReads: [''] });
  await assert.rejects(clipboard.invoke(), /Copy your Gemini API key first/);
  assert.equal(clipboard.fallbackCalls, 1);
  assert.equal(clipboard.clears, 0);
});

test('does not expose the clipboard key through the preload API', async () => {
  const exposed = {};
  const calls = [];
  const electronMock = {
    contextBridge: { exposeInMainWorld: (name, api) => { exposed[name] = api; } },
    ipcRenderer: {
      invoke: (...args) => { calls.push(args); return Promise.resolve({ status: 'READY' }); },
      on: () => {},
      removeListener: () => {},
      send: () => {},
    },
  };
  const preloadPath = path.join(__dirname, 'preload.cjs');
  const source = fs.readFileSync(preloadPath, 'utf8');
  vm.runInNewContext(source, {
    require: (name) => {
      assert.equal(name, 'electron');
      return electronMock;
    },
  });

  await exposed.rubyDesktop.runtime.configureGeminiFromClipboard();
  assert.deepEqual(calls, [[channel]]);
  assert.equal('key' in exposed.rubyDesktop.runtime, false);
});
