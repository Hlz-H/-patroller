import { app, BrowserWindow, ipcMain, shell } from 'electron';
import path from 'path';
import { createTray } from './tray';

let mainWindow: BrowserWindow | null = null;

const isDev = !app.isPackaged;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: '巡查者 - Commander',
    frame: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

function setupIPC(): void {
  ipcMain.handle('get-app-status', () => {
    return {
      version: app.getVersion(),
      electronVersion: process.versions.electron,
      nodeVersion: process.versions.node,
      platform: process.platform,
      arch: process.arch,
    };
  });

  ipcMain.handle('open-devtools', () => {
    mainWindow?.webContents.openDevTools({ mode: 'detach' });
    return true;
  });

  ipcMain.handle('minimize-window', () => {
    mainWindow?.minimize();
    return true;
  });

  ipcMain.handle('hide-window', () => {
    mainWindow?.hide();
    return true;
  });

  ipcMain.handle('show-window', () => {
    mainWindow?.show();
    mainWindow?.focus();
    return true;
  });
}

app.whenReady().then(() => {
  createWindow();
  createTray(mainWindow!);
  setupIPC();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else {
      mainWindow?.show();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  mainWindow = null;
});
