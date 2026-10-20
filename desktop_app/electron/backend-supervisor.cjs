const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const startupErrorForUi = (error) => {
  const message = error?.message || '';
  if (message === 'Ruby’s bundled assistant runtime is missing. Reinstall Ruby.' ||
      message === 'The assistant did not become ready in time.' ||
      message === 'Ruby could not launch its assistant runtime.' ||
      /^Ruby assistant exited during startup \(code (?:-?\d+|unknown)\)\.$/.test(message)) return message;
  return 'Ruby could not launch its assistant runtime. Check the installation and try again.';
};

class BackendSupervisor {
  constructor({ app, safeStorage, spawnProcess = spawn, fetchImpl = fetch, onState = () => {}, env = process.env,
    platform = process.platform, resourcesPath = process.resourcesPath, projectRoot = path.resolve(__dirname, '../..') } = {}) {
    this.app = app;
    this.safeStorage = safeStorage;
    this.spawnProcess = spawnProcess;
    this.fetchImpl = fetchImpl;
    this.onState = onState;
    this.env = env;
    this.platform = platform;
    this.resourcesPath = resourcesPath;
    this.projectRoot = projectRoot;
    this.child = null;
    this.baseUrl = '';
    this.token = '';
    this.intentionalStop = false;
    this.restarts = 0;
    this.state = { status: 'STARTING', message: 'Starting Ruby…' };
    this.stopFile = path.join(app.getPath('temp'), `ruby-shutdown-${process.pid}-${crypto.randomUUID()}`);
  }

  setState(status, message, error = '') {
    this.state = { status, message, ...(error ? { error } : {}) };
    this.onState(this.state);
  }

  get keyPath() { return path.join(this.app.getPath('userData'), 'gemini-key.bin'); }

  readKey() {
    if (!fs.existsSync(this.keyPath)) return '';
    if (!this.safeStorage?.isEncryptionAvailable()) throw new Error('Secure key storage is not available on this Windows account.');
    return this.safeStorage.decryptString(fs.readFileSync(this.keyPath)).trim();
  }

  writeKey(key) {
    if (!this.safeStorage?.isEncryptionAvailable()) throw new Error('Secure key storage is not available on this Windows account.');
    fs.mkdirSync(this.app.getPath('userData'), { recursive: true });
    const encrypted = this.safeStorage.encryptString(key);
    const tempPath = `${this.keyPath}.tmp`;
    fs.writeFileSync(tempPath, encrypted);
    fs.renameSync(tempPath, this.keyPath);
  }

  backendCommand() {
    if (this.app.isPackaged) {
      const exe = path.join(this.resourcesPath, 'backend', 'ruby-backend.exe');
      if (!fs.existsSync(exe)) throw new Error('Ruby’s bundled assistant runtime is missing. Reinstall Ruby.');
      return { command: exe, prefix: [], cwd: path.dirname(exe) };
    }
    const python = this.env.RUBY_PYTHON_EXECUTABLE || (this.platform === 'win32' ? 'python' : 'python3');
    return { command: python, prefix: ['-m', 'background_agent.bridge.production_server'], cwd: this.projectRoot };
  }

  childEnv(key, token = crypto.randomBytes(32).toString('base64url')) {
    return { ...this.env, GEMINI_API_KEY: key, RUBY_BRIDGE_TOKEN: token };
  }

  async validateKey(key) {
    const { command, prefix, cwd } = this.backendCommand();
    return new Promise((resolve, reject) => {
      let settled = false;
      let timer;
      const finish = (error) => {
        if (settled) return;
        settled = true;
        if (timer) clearTimeout(timer);
        if (error) reject(error); else resolve();
      };
      let child;
      try {
        child = this.spawnProcess(command, [...prefix, '--validate-gemini'], {
          cwd, env: this.childEnv(key), windowsHide: true, stdio: ['ignore', 'ignore', 'ignore'],
        });
      } catch {
        finish(new Error('Ruby could not start its bundled assistant runtime.'));
        return;
      }
      timer = setTimeout(() => { child.kill(); finish(new Error('Gemini key validation timed out. Check your connection and try again.')); }, 25000);
      child.once('error', () => finish(new Error('Ruby could not start its bundled assistant runtime.')));
      child.once('exit', (code) => finish(code === 0 ? null : new Error('Gemini could not validate this key. Check the key and network connection.')));
    });
  }

  async start() {
    let key;
    try { key = this.readKey(); }
    catch (error) { this.setState('BACKEND_ERROR', 'Ruby needs secure local key storage.', error.message); return; }
    if (!key) { this.setState('CONFIGURATION_REQUIRED', 'Add your Gemini API key to get started.'); return; }
    await this.startWithKey(key);
  }

  async configureKey(input) {
    const key = typeof input === 'string' ? input.trim() : '';
    if (key.length < 20 || key.length > 500 || /[\r\n\0]/.test(key)) throw new Error('Enter a valid Gemini API key.');
    const previousState = this.state;
    this.setState('INITIALIZING', 'Checking your Gemini API key…');
    try {
      await this.validateKey(key);
      this.writeKey(key);
      await this.stop();
      this.restarts = 0;
      await this.startWithKey(key);
      if (this.state.status !== 'READY') {
        throw new Error(this.state.error || this.state.message || 'Ruby could not start after validating the Gemini API key.');
      }
      return true;
    } catch (error) {
      const safeMessage = error.message || 'Ruby could not configure Gemini.';
      if (previousState.status === 'READY') this.setState('READY', 'Ruby is ready.');
      else this.setState('CONFIGURATION_REQUIRED', safeMessage);
      throw new Error(safeMessage);
    }
  }

  async startWithKey(key) {
    this.setState('INITIALIZING', 'Preparing Ruby’s assistant…');
    try {
      const { command, prefix, cwd } = this.backendCommand();
      const args = [...prefix, '--managed', '--host', '127.0.0.1', '--port', '0', '--shutdown-file', this.stopFile];
      const token = crypto.randomBytes(32).toString('base64url');
      this.token = token;
      this.intentionalStop = false;
      const child = this.spawnProcess(command, args, {
        cwd, env: this.childEnv(key, token), windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
      });
      this.child = child;
      child.stderr?.on('data', () => {});
      this.setState('WAITING_FOR_BACKEND', 'Connecting to Ruby’s assistant…');
      const baseUrl = await this.waitForReady(child);
      this.baseUrl = baseUrl;
      this.setState('READY', 'Ruby is ready.');
      child.once('exit', (code) => this.handleExit(child, code, key));
    } catch (error) {
      await this.stop();
      this.setState('BACKEND_ERROR', 'Ruby could not start its assistant.', startupErrorForUi(error));
    }
  }

  waitForReady(child) {
    return new Promise((resolve, reject) => {
      let buffer = '';
      let settled = false;
      const finish = (error, url) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (error) reject(error); else resolve(url);
      };
      const timer = setTimeout(() => { child.kill(); finish(new Error('The assistant did not become ready in time.')); }, 30000);
      child.stdout?.on('data', async (chunk) => {
        if (this.baseUrl) return;
        buffer += chunk.toString();
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() || '';
        for (const line of lines) {
          const match = line.match(/^RUBY_BRIDGE_READY=(http:\/\/127\.0\.0\.1:\d+)$/);
          if (!match) continue;
          try {
            const response = await this.fetchImpl(`${match[1]}/v1/health`, { signal: AbortSignal.timeout(3000) });
            if (response.ok) finish(null, match[1]);
          } catch { /* keep waiting until the startup deadline */ }
        }
      });
      child.once('error', () => finish(new Error('Ruby could not launch its assistant runtime.')));
      child.once('exit', (code) => finish(new Error(`Ruby assistant exited during startup (code ${code ?? 'unknown'}).`)));
    });
  }

  async handleExit(child, code, key) {
    if (this.child !== child || this.intentionalStop) return;
    this.child = null;
    this.baseUrl = '';
    this.setState('BACKEND_ERROR', `Ruby’s assistant stopped unexpectedly (code ${code ?? 'unknown'}).`, 'Trying to restart…');
    if (this.restarts >= 2) {
      this.setState('BACKEND_ERROR', 'Ruby’s assistant stopped and could not recover.', 'Close and reopen Ruby, or reinstall the app if the problem continues.');
      return;
    }
    const delay = this.restarts === 0 ? 750 : 2000;
    this.restarts += 1;
    await sleep(delay);
    if (this.intentionalStop) return;
    await this.startWithKey(key);
  }

  async stop() {
    const child = this.child;
    if (!child) return;
    this.intentionalStop = true;
    try { fs.writeFileSync(this.stopFile, 'stop'); } catch { /* process may already be closing */ }
    if (child.exitCode === null) await Promise.race([new Promise((resolve) => child.once('exit', resolve)), sleep(4000)]);
    if (child.exitCode === null && !child.killed) child.kill();
    this.child = null;
    this.baseUrl = '';
    try { fs.rmSync(this.stopFile, { force: true }); } catch { /* temp file cleanup is best effort */ }
  }

  async request(route, options = {}) {
    if (this.state.status !== 'READY' || !this.baseUrl) throw new Error(this.state.error || this.state.message);
    const response = await this.fetchImpl(`${this.baseUrl}${route}`, {
      ...options,
      headers: { ...(options.body ? { 'content-type': 'application/json' } : {}), authorization: `Bearer ${this.token}`, ...options.headers },
      signal: AbortSignal.timeout(5000),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body?.error?.message || `Ruby bridge returned HTTP ${response.status}`);
    return body;
  }
}

module.exports = { BackendSupervisor };
