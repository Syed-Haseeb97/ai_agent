const { app, BrowserWindow, ipcMain, screen, safeStorage, clipboard } = require('electron');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { registerClipboardKeyHandler } = require('./clipboard-key.cjs');
const { BackendSupervisor } = require('./backend-supervisor.cjs');
const { BridgeEventPump } = require('./bridge-events.cjs');

const ORB_SIZE = 110;
const ORB_MARGIN = 18;
const CONTROL_WIDTH = 1240;
const CONTROL_HEIGHT = 820;
const CONTROL_MIN_WIDTH = 850;
const CONTROL_MIN_HEIGHT = 620;
const EXECUTION_MODES = new Set(['cursor_control', 'task_doing', 'background_task']);

let mainWindow;
let orbWindow;
let backend;
let bridgeEvents;
let quitting = false;

function broadcastToRenderers(channel, payload) {
  for (const win of [mainWindow, orbWindow]) {
    if (!win || win.isDestroyed()) continue;
    try {
      win.webContents.send(channel, payload);
    } catch {
      // A renderer can disappear between the destroyed check and the send.
    }
  }
}

function orbBounds() {
  const display = mainWindow && !mainWindow.isDestroyed()
    ? screen.getDisplayMatching(mainWindow.getBounds())
    : screen.getPrimaryDisplay();
  const { x, y, width, height } = display.workArea;
  return {
    x: Math.round(x + width - ORB_SIZE - ORB_MARGIN),
    y: Math.round(y + height - ORB_SIZE - ORB_MARGIN),
    width: ORB_SIZE,
    height: ORB_SIZE,
  };
}

function rendererPreferences() {
  return {
    preload: path.join(__dirname, 'preload.cjs'),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    backgroundThrottling: false,
  };
}

function logRendererDiagnostics(win, name) {
  win.webContents.on('did-fail-load', (_event, errorCode, _errorDescription, _validatedURL, isMainFrame) => {
    console.error(`[Electron] ${name} renderer failed to load (code ${errorCode}, main frame: ${isMainFrame})`);
  });
  win.webContents.on('console-message', (details) => {
    if (details.level === 'error') {
      console.error(`[Electron] ${name} renderer console error at ${details.sourceId}:${details.lineNumber}`);
    }
  });
  win.webContents.on('render-process-gone', (_event, details) => {
    console.error(`[Electron] ${name} renderer process gone (reason: ${details.reason}, exit code: ${details.exitCode})`);
  });
}

function loadRenderer(win, hash) {
  if (app.isPackaged) {
    const entry = path.join(__dirname, '..', 'dist', 'index.html');
    win.webContents.on('will-navigate', (event, url) => {
      if (url !== pathToFileURL(entry).href) event.preventDefault();
    });
    win.loadFile(entry, hash ? { hash } : {});
    return;
  }
  win.webContents.on('will-navigate', (event, url) => {
    let allowed = false;
    try { allowed = new URL(url).origin === 'http://127.0.0.1:5173'; } catch {}
    if (!allowed) event.preventDefault();
  });
  win.loadURL(hash ? `http://127.0.0.1:5173/#${hash}` : 'http://127.0.0.1:5173');
}

function createMainWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  mainWindow = new BrowserWindow({
    width: Math.min(CONTROL_WIDTH, width - 80),
    height: Math.min(CONTROL_HEIGHT, height - 80),
    minWidth: CONTROL_MIN_WIDTH,
    minHeight: CONTROL_MIN_HEIGHT,
    resizable: true,
    frame: false,
    backgroundColor: '#080a0f',
    show: false,
    autoHideMenuBar: true,
    webPreferences: rendererPreferences(),
  });

  mainWindow.center();
  logRendererDiagnostics(mainWindow, 'main');
  mainWindow.once('ready-to-show', () => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show();
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.on('minimize', (event) => {
    event.preventDefault();
    collapseToOrb();
  });
  mainWindow.on('close', (event) => {
    if (quitting) return;
    event.preventDefault();
    collapseToOrb();
  });
  mainWindow.on('closed', () => { mainWindow = null; });
  loadRenderer(mainWindow);
}

function createOrbWindow() {
  orbWindow = new BrowserWindow({
    ...orbBounds(),
    minWidth: ORB_SIZE,
    minHeight: ORB_SIZE,
    resizable: false,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    show: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    autoHideMenuBar: true,
    webPreferences: rendererPreferences(),
  });

  logRendererDiagnostics(orbWindow, 'orb');
  orbWindow.setAlwaysOnTop(true, 'floating');
  orbWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  orbWindow.on('close', (event) => {
    if (quitting) return;
    event.preventDefault();
  });
  orbWindow.on('closed', () => { orbWindow = null; });
  loadRenderer(orbWindow, 'orb');
}

function showMainWindow() {
  if (orbWindow && !orbWindow.isDestroyed()) orbWindow.hide();
  if (!mainWindow || mainWindow.isDestroyed()) {
    createMainWindow();
    return;
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function collapseToOrb() {
  if (!orbWindow || orbWindow.isDestroyed()) {
    createOrbWindow();
    orbWindow.once('ready-to-show', () => {
      if (orbWindow && !orbWindow.isDestroyed()) orbWindow.showInactive();
    });
  } else {
    orbWindow.setBounds(orbBounds());
    orbWindow.showInactive();
  }
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.hide();
}

ipcMain.on('ruby:window:minimize', () => collapseToOrb());
ipcMain.on('ruby:window:close', () => collapseToOrb());
ipcMain.on('ruby:window:show', () => showMainWindow());
ipcMain.on('ruby:window:toggle-maximize', () => {
  if (!mainWindow) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});

ipcMain.handle('ruby:runtime:state', async () => backend?.state || { status: 'STARTING', message: 'Starting Ruby…' });
registerClipboardKeyHandler({ ipcMain, clipboard, getBackend: () => backend });
ipcMain.handle('ruby:bridge:state', async () => backend.request('/v1/state'));
ipcMain.handle('ruby:bridge:chat', async (_event, payload) => {
  if (!payload || typeof payload !== 'object') throw new Error('Invalid chat payload.');
  const message = typeof payload.message === 'string' ? payload.message.trim() : '';
  const conversationId = typeof payload.conversationId === 'string' ? payload.conversationId : '';
  if (!message || message.length > 8000) throw new Error('Enter a message up to 8,000 characters.');
  if (conversationId.length > 128) throw new Error('Invalid conversation ID.');
  return backend.request('/v1/chat', {
    method: 'POST',
    body: JSON.stringify({ message, conversationId: conversationId || null }),
  });
});
ipcMain.handle('ruby:bridge:submit', async (_event, task) => {
  if (!task || typeof task !== 'object') throw new Error('Invalid task payload.');
  const goal = typeof task.goal === 'string' ? task.goal.trim() : '';
  if (!goal || goal.length > 4000) throw new Error('Enter a task up to 4,000 characters.');
  if (!EXECUTION_MODES.has(task.executionMode)) throw new Error('Choose a valid execution mode.');
  const created = await backend.request('/v1/tasks', { method: 'POST', body: JSON.stringify({ goal, executionMode: task.executionMode }) });
  void bridgeEvents?.refresh();
  return created;
});
ipcMain.handle('ruby:bridge:cancel', async (_event, taskId) => {
  if (typeof taskId !== 'string' || !/^[a-f0-9-]{16,64}$/i.test(taskId)) throw new Error('Invalid task id.');
  const result = await backend.request(`/v1/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' });
  void bridgeEvents?.refresh();
  return result;
});
ipcMain.handle('ruby:bridge:confirm', async (_event, confirmationId, approved) => {
  if (typeof confirmationId !== 'string' || !/^[a-f0-9-]{16,64}$/i.test(confirmationId) || typeof approved !== 'boolean') throw new Error('Invalid confirmation response.');
  const result = await backend.request(`/v1/confirmations/${encodeURIComponent(confirmationId)}`, { method: 'POST', body: JSON.stringify({ approved }) });
  void bridgeEvents?.refresh();
  return result;
});

app.whenReady().then(() => {
  app.setAppUserModelId('com.ruby.agentdesktop');
  backend = new BackendSupervisor({ app, safeStorage, onState: (state) => {
    broadcastToRenderers('ruby:runtime:changed', state);
    if (state.status === 'READY') void bridgeEvents?.refresh();
  } });
  bridgeEvents = new BridgeEventPump({
    request: (url) => backend.request(url),
    getBackendState: () => backend?.state,
    broadcast: broadcastToRenderers,
  });
  createMainWindow();
  createOrbWindow();
  bridgeEvents.start();
  backend.start();
  app.on('activate', () => showMainWindow());
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', (event) => {
  if (!quitting && backend) {
    event.preventDefault();
    quitting = true;
    bridgeEvents?.stop();
    backend.stop().finally(() => app.quit());
    return;
  }
  bridgeEvents?.stop();
  for (const channel of ['ruby:bridge:state', 'ruby:bridge:chat', 'ruby:bridge:submit', 'ruby:bridge:cancel', 'ruby:bridge:confirm']) ipcMain.removeHandler(channel);
});
