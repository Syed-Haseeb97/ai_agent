const { contextBridge, ipcRenderer } = require('electron');

const subscribe = (channel, callback) => {
  if (typeof callback !== 'function') throw new TypeError('callback must be a function');
  const listener = (_event, payload) => callback(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
};

contextBridge.exposeInMainWorld('rubyDesktop', Object.freeze({
  minimize: () => ipcRenderer.send('ruby:window:minimize'),
  show: () => ipcRenderer.send('ruby:window:show'),
  toggleMaximize: () => ipcRenderer.send('ruby:window:toggle-maximize'),
  close: () => ipcRenderer.send('ruby:window:close'),
  runtime: Object.freeze({
    getState: () => ipcRenderer.invoke('ruby:runtime:state'),
    configureGeminiFromClipboard: () => ipcRenderer.invoke('ruby:runtime:configure-key-from-clipboard'),
    onState: (callback) => subscribe('ruby:runtime:changed', callback),
  }),
  bridge: Object.freeze({
    getState: () => ipcRenderer.invoke('ruby:bridge:state'),
    submitTask: (task) => ipcRenderer.invoke('ruby:bridge:submit', task),
    cancelTask: (taskId) => ipcRenderer.invoke('ruby:bridge:cancel', taskId),
    respondConfirmation: (id, approved) => ipcRenderer.invoke('ruby:bridge:confirm', id, approved),
    onState: (callback) => subscribe('ruby:bridge:changed', callback),
    onTask: (callback) => subscribe('ruby:bridge:task', callback),
    onActivity: (callback) => subscribe('ruby:bridge:activity', callback),
  }),
}));
