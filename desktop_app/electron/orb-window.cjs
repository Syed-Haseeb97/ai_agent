'use strict';

const ORB_SIZE = 110;
const ORB_MARGIN = 18;

function clampOrbPosition(x, y, workArea, size = ORB_SIZE) {
  const maxX = workArea.x + Math.max(0, workArea.width - size);
  const maxY = workArea.y + Math.max(0, workArea.height - size);
  return {
    x: Math.round(Math.min(maxX, Math.max(workArea.x, x))),
    y: Math.round(Math.min(maxY, Math.max(workArea.y, y))),
  };
}

function initialOrbBounds(workArea, size = ORB_SIZE, margin = ORB_MARGIN) {
  const position = clampOrbPosition(
    workArea.x + workArea.width - size - margin,
    workArea.y + workArea.height - size - margin,
    workArea,
    size,
  );
  return { ...position, width: size, height: size };
}

function collapseOrbWindow({ orbWindow, createOrbWindow, initialBounds }) {
  if (!orbWindow || orbWindow.isDestroyed()) {
    const created = createOrbWindow(initialBounds);
    created.once('ready-to-show', () => {
      if (!created.isDestroyed()) created.showInactive();
    });
    return created;
  }
  orbWindow.showInactive();
  return orbWindow;
}

function hideOrbForExpansion(orbWindow) {
  if (orbWindow && !orbWindow.isDestroyed()) orbWindow.hide();
}

function registerOrbDragHandlers({ ipcMain, screen, getOrbWindow }) {
  let dragOffset = null;

  function ownedOrb(event) {
    const win = getOrbWindow();
    return win && !win.isDestroyed() && event.sender === win.webContents ? win : null;
  }

  function start(event) {
    const win = ownedOrb(event);
    if (!win) return;
    const pointer = screen.getCursorScreenPoint();
    const bounds = win.getBounds();
    dragOffset = { x: bounds.x - pointer.x, y: bounds.y - pointer.y };
  }

  function move(event) {
    const win = ownedOrb(event);
    if (!win || !dragOffset) return;
    const pointer = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(pointer);
    const position = clampOrbPosition(
      pointer.x + dragOffset.x,
      pointer.y + dragOffset.y,
      display.workArea,
    );
    win.setPosition(position.x, position.y);
  }

  function end(event) {
    if (ownedOrb(event)) dragOffset = null;
  }

  ipcMain.on('ruby:orb:drag-start', start);
  ipcMain.on('ruby:orb:drag-move', move);
  ipcMain.on('ruby:orb:drag-end', end);

  return {
    reset: () => { dragOffset = null; },
    dispose: () => {
      ipcMain.removeListener('ruby:orb:drag-start', start);
      ipcMain.removeListener('ruby:orb:drag-move', move);
      ipcMain.removeListener('ruby:orb:drag-end', end);
      dragOffset = null;
    },
  };
}

module.exports = {
  ORB_MARGIN,
  ORB_SIZE,
  clampOrbPosition,
  collapseOrbWindow,
  hideOrbForExpansion,
  initialOrbBounds,
  registerOrbDragHandlers,
};
