const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('rubyDesktop', Object.freeze({
  minimize: () => ipcRenderer.send('ruby:window:minimize'),
  toggleMaximize: () => ipcRenderer.send('ruby:window:toggle-maximize'),
  close: () => ipcRenderer.send('ruby:window:close'),
  setExpanded: (expanded) => ipcRenderer.send('ruby:window:expanded', Boolean(expanded)),
  bridge: Object.freeze({
    getState: () => ipcRenderer.invoke('ruby:bridge:state'),
    submitTask: (goal) => ipcRenderer.invoke('ruby:bridge:submit', goal),
    cancelTask: (taskId) => ipcRenderer.invoke('ruby:bridge:cancel', taskId),
    respondConfirmation: (id, approved) => ipcRenderer.invoke('ruby:bridge:confirm', id, approved),
  }),
}));
