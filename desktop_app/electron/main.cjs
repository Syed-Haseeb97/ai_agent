const { app, BrowserWindow, ipcMain, screen, safeStorage, clipboard } = require('electron');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { BackendSupervisor } = require('./backend-supervisor.cjs');

let mainWindow;
let backend;
let quitting = false;

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

ipcMain.handle('ruby:runtime:state', async () => backend?.state || { status: 'STARTING', message: 'Starting Ruby…' });
ipcMain.handle('ruby:runtime:configure-key-from-clipboard', async () => {
  const key = clipboard.readText();
  if (typeof key !== 'string' || !key.trim()) throw new Error('Copy your Gemini API key first, then choose Paste key and start Ruby.');
  const configured = await backend.configureKey(key);
  if (configured && clipboard.readText() === key) clipboard.clear();
  return backend.state;
});
ipcMain.handle('ruby:bridge:state', async () => backend.request('/v1/state'));
ipcMain.handle('ruby:bridge:submit', async (_event, goal) => {
  if (typeof goal !== 'string' || !goal.trim() || goal.length > 4000) throw new Error('Enter a task up to 4,000 characters.');
  return backend.request('/v1/tasks', { method: 'POST', body: JSON.stringify({ goal: goal.trim() }) });
});
ipcMain.handle('ruby:bridge:cancel', async (_event, taskId) => {
  if (typeof taskId !== 'string' || !/^[a-f0-9-]{16,64}$/i.test(taskId)) throw new Error('Invalid task id.');
  return backend.request(`/v1/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' });
});
ipcMain.handle('ruby:bridge:confirm', async (_event, confirmationId, approved) => {
  if (typeof confirmationId !== 'string' || !/^[a-f0-9-]{16,64}$/i.test(confirmationId) || typeof approved !== 'boolean') throw new Error('Invalid confirmation response.');
  return backend.request(`/v1/confirmations/${encodeURIComponent(confirmationId)}`, { method: 'POST', body: JSON.stringify({ approved }) });
});

app.whenReady().then(() => {
  app.setAppUserModelId('com.ruby.agentdesktop');
  backend = new BackendSupervisor({ app, safeStorage, onState: (state) => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('ruby:runtime:changed', state);
  } });
  createWindow();
  backend.start();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', (event) => {
  if (!quitting && backend) {
    event.preventDefault();
    quitting = true;
    backend.stop().finally(() => app.quit());
    return;
  }
  for (const channel of ['ruby:bridge:state', 'ruby:bridge:submit', 'ruby:bridge:cancel', 'ruby:bridge:confirm']) ipcMain.removeHandler(channel);
});
