const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');

let mainWindow;

function bridgeConfig() {
  const config = { ...process.env };
  // The dev bridge writes its URL and bearer token here. Read it in the privileged
  // host process; never inject the token into Vite/React's renderer bundle.
  const envPath = path.join(__dirname, '..', '.env.local');
  try {
    for (const line of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
      const match = line.match(/^\s*RUBY_BRIDGE_(URL|TOKEN)\s*=\s*(.*?)\s*$/);
      if (match && !config[`RUBY_BRIDGE_${match[1]}`]) config[`RUBY_BRIDGE_${match[1]}`] = match[2].replace(/^['"]|['"]$/g, '');
    }
  } catch {}
  const rawUrl = config.RUBY_BRIDGE_URL || 'http://127.0.0.1:8765';
  let url;
  try { url = new URL(rawUrl); } catch { throw new Error('Ruby bridge URL is invalid'); }
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) {
    throw new Error('Ruby bridge must use HTTP on loopback');
  }
  return { baseUrl: url.origin, token: config.RUBY_BRIDGE_TOKEN || '' };
}

async function bridgeRequest(route, options = {}) {
  const { baseUrl, token } = bridgeConfig();
  const response = await fetch(`${baseUrl}${route}`, {
    ...options,
    headers: { ...(options.body ? { 'content-type': 'application/json' } : {}),
      ...(token ? { authorization: `Bearer ${token}` } : {}), ...options.headers },
    signal: AbortSignal.timeout(5000),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body?.error?.message || `Ruby bridge returned HTTP ${response.status}`);
  return body;
}

function placeWindow(isExpanded) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  if (isExpanded) {
    mainWindow.setResizable(true);
    mainWindow.setMinimumSize(850, 620);
    mainWindow.setSize(1240, 820, true);
    mainWindow.center();
    mainWindow.setBackgroundColor('#080a0f');
  } else {
    const display = screen.getDisplayMatching(mainWindow.getBounds());
    const { x, y, width, height } = display.workArea;
    const size = 110;
    mainWindow.setMinimumSize(size, size);
    mainWindow.setResizable(false);
    mainWindow.setSize(size, size, true);
    mainWindow.setPosition(x + width - size - 18, y + height - size - 18, false);
    mainWindow.setBackgroundColor('#00000000');
  }
}

function createWindow() {
  const display = screen.getPrimaryDisplay();
  const { x, y, width, height } = display.workArea;
  const size = 110;
  mainWindow = new BrowserWindow({
    width: size,
    height: size,
    x: x + width - size - 18,
    y: y + height - size - 18,
    minWidth: size,
    minHeight: size,
    resizable: false,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  if (app.isPackaged) {
    const entry = path.join(__dirname, '..', 'dist', 'index.html');
    mainWindow.webContents.on('will-navigate', (event, url) => {
      if (url !== pathToFileURL(entry).href) event.preventDefault();
    });
    mainWindow.loadFile(entry);
  } else {
    mainWindow.webContents.on('will-navigate', (event, url) => {
      let allowed = false;
      try { allowed = new URL(url).origin === 'http://127.0.0.1:5173'; } catch {}
      if (!allowed) event.preventDefault();
    });
    mainWindow.loadURL('http://127.0.0.1:5173');
  }
}

ipcMain.on('ruby:window:minimize', () => mainWindow?.minimize());
ipcMain.on('ruby:window:toggle-maximize', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});
ipcMain.on('ruby:window:close', () => mainWindow?.close());
ipcMain.on('ruby:window:expanded', (_event, value) => {
  if (typeof value === 'boolean') placeWindow(value);
});

ipcMain.handle('ruby:bridge:state', async () => bridgeRequest('/v1/state'));
ipcMain.handle('ruby:bridge:submit', async (_event, goal) => {
  if (typeof goal !== 'string' || !goal.trim() || goal.length > 4000) throw new Error('Enter a task up to 4,000 characters.');
  return bridgeRequest('/v1/tasks', { method: 'POST', body: JSON.stringify({ goal: goal.trim() }) });
});
ipcMain.handle('ruby:bridge:cancel', async (_event, taskId) => {
  if (typeof taskId !== 'string' || !/^[a-f0-9-]{16,64}$/i.test(taskId)) throw new Error('Invalid task id.');
  return bridgeRequest(`/v1/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' });
});
ipcMain.handle('ruby:bridge:confirm', async (_event, confirmationId, approved) => {
  if (typeof confirmationId !== 'string' || !/^[a-f0-9-]{16,64}$/i.test(confirmationId) || typeof approved !== 'boolean') throw new Error('Invalid confirmation response.');
  return bridgeRequest(`/v1/confirmations/${encodeURIComponent(confirmationId)}`, { method: 'POST', body: JSON.stringify({ approved }) });
});

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  for (const channel of ['ruby:bridge:state', 'ruby:bridge:submit', 'ruby:bridge:cancel', 'ruby:bridge:confirm']) ipcMain.removeHandler(channel);
});
