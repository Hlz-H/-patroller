import type { WSMessage } from '../types';

type MessageHandler = (msg: WSMessage) => void;

const MAX_RETRIES = 10;
const RETRY_DELAY = 3000;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private handlers: MessageHandler[] = [];
  private retryCount = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;

  connect(): void {
    if (this.destroyed) return;

    try {
      this.ws = new WebSocket('ws://localhost:8099/ws');

      this.ws.onopen = () => {
        console.log('[WS] 已连接');
        this.retryCount = 0;
        this.dispatch({ type: 'status', data: null as never }); // trigger connected state
      };

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const msg: WSMessage = JSON.parse(event.data);
          this.dispatch(msg);
        } catch (err) {
          console.error('[WS] 消息解析失败:', err);
        }
      };

      this.ws.onclose = () => {
        console.log('[WS] 连接关闭');
        this.ws = null;
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.error('[WS] 连接错误:', err);
      };
    } catch (err) {
      console.error('[WS] 创建连接失败:', err);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.destroyed || this.retryCount >= MAX_RETRIES) return;

    this.retryCount++;
    console.log(`[WS] 将在 ${RETRY_DELAY / 1000}s 后重连 (第 ${this.retryCount} 次)`);

    this.retryTimer = setTimeout(() => {
      this.connect();
    }, RETRY_DELAY);
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  private dispatch(msg: WSMessage): void {
    for (const handler of this.handlers) {
      try {
        handler(msg);
      } catch (err) {
        console.error('[WS] 处理消息时出错:', err);
      }
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  destroy(): void {
    this.destroyed = true;
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.handlers = [];
  }
}

export const wsClient = new WebSocketClient();
