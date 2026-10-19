const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

let mainWindow;

function placeWindow(isExpanded) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  if (expanded) {
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

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
