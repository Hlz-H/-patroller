import { BrowserWindow, Tray, Menu, nativeImage, app } from 'electron';
import path from 'path';

let tray: Tray | null = null;

function createShieldIcon(): Electron.NativeImage {
  // Create a simple 16x16 shield icon using raw pixel data (RGBA)
  const size = 16;
  const buffer = Buffer.alloc(size * size * 4, 0);

  // Draw a shield shape
  const draw = (x: number, y: number, r: number, g: number, b: number, a: number = 255) => {
    if (x >= 0 && x < size && y >= 0 && y < size) {
      const idx = (y * size + x) * 4;
      buffer[idx] = r;
      buffer[idx + 1] = g;
      buffer[idx + 2] = b;
      buffer[idx + 3] = a;
    }
  };

  // Simple shield pattern (cyan/teal color)
  const cx = 8;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      // Shield shape: top triangle narrowing to point, then widening rectangle
      const halfWidth = Math.max(0, Math.min(7, y < 6 ? (y + 2) : 7));
      if (Math.abs(x - cx) <= halfWidth && y < 14) {
        // Border
        const onBorder =
          Math.abs(x - cx) === halfWidth ||
          y === 0 ||
          (y < 6 && Math.abs(x - cx) === halfWidth - 1) ||
          y === 13;
        if (onBorder) {
          draw(x, y, 0, 180, 220);
        } else {
          draw(x, y, 0, 140, 180, 200);
        }
      }
    }
  }

  // draw an exclamation mark in center
  for (let dy = 3; dy <= 8; dy++) {
    const row = [
      (dy === 3 || dy === 4) ? [cx - 1, cx, cx + 1] :
        (dy === 5 || dy === 6) ? [cx] :
          (dy === 8) ? [cx - 1, cx, cx + 1] : [],
    ];
    const cols = row[dy - 3] || [];
    for (const colX of cols) {
      draw(colX, dy, 255, 255, 255);
    }
  }

  return nativeImage.createFromBuffer(buffer, {
    width: size,
    height: size,
  });
}

export function createTray(mainWindow: BrowserWindow): void {
  const icon = createShieldIcon();
  tray = new Tray(icon);
  tray.setToolTip('巡查者 - Commander');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示窗口',
      click: () => {
        mainWindow.show();
        mainWindow.focus();
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  tray.on('click', () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}
