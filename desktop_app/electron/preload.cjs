const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('rubyDesktop', Object.freeze({
  minimize: () => ipcRenderer.send('ruby:window:minimize'),
  toggleMaximize: () => ipcRenderer.send('ruby:window:toggle-maximize'),
  close: () => ipcRenderer.send('ruby:window:close'),
  setExpanded: (expanded) => ipcRenderer.send('ruby:window:expanded', Boolean(expanded)),
}));
