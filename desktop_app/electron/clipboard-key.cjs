const { execFile } = require('node:child_process');

const CONFIGURE_KEY_CHANNEL = 'ruby:runtime:configure-key-from-clipboard';
const EMPTY_CLIPBOARD_MESSAGE = 'Copy your Gemini API key first, then choose Paste key and start Ruby.';

function readWindowsClipboardText(execFileImpl) {
  return new Promise((resolve, reject) => {
    execFileImpl('powershell.exe', [
      '-NoProfile',
      '-NonInteractive',
      '-Command',
      '[Console]::Write((Get-Clipboard -Raw))',
    ], {
      encoding: 'utf8',
      maxBuffer: 64 * 1024,
      timeout: 2000,
      windowsHide: true,
    }, (error, stdout) => {
      if (error) {
        reject(new Error('Could not read the Windows clipboard. Copy your Gemini API key and try again.'));
        return;
      }
      resolve(stdout);
    });
  });
}

function registerClipboardKeyHandler({
  ipcMain,
  clipboard,
  getBackend,
  platform = process.platform,
  execFileImpl = execFile,
}) {
  const readText = async () => {
    const text = clipboard.readText();
    if (typeof text === 'string' && text.trim()) return text;
    if (platform === 'win32') return readWindowsClipboardText(execFileImpl);
    return text;
  };

  ipcMain.handle(CONFIGURE_KEY_CHANNEL, async () => {
    const key = await readText();
    if (typeof key !== 'string' || !key.trim()) throw new Error(EMPTY_CLIPBOARD_MESSAGE);

    const backend = getBackend();
    const configured = await backend.configureKey(key);
    if (configured && await readText() === key) clipboard.clear();
    return backend.state;
  });
}

module.exports = { registerClipboardKeyHandler };
