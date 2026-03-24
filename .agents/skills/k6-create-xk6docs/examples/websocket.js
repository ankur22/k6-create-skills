/**
 * k6 WebSocket example — k6/experimental/websockets
 *
 * Covers: WebSocket constructor, addEventListener, send/receive/close,
 *         error handling, check(), shared-iterations scenario
 *
 * Note: use k6/experimental/websockets for new scripts (not the legacy k6/ws).
 * The default function must be synchronous — WebSocket events resolve in the
 * k6 event loop automatically.
 */
import { WebSocket } from 'k6/experimental/websockets';
import { check } from 'k6';

const WS_URL = 'wss://quickpizza.grafana.com/ws';

export const options = {
  scenarios: {
    ws_load: {
      executor: 'shared-iterations',
      vus: 5,
      iterations: 20,
      maxDuration: '2m',
    },
  },
  thresholds: {
    ws_session_duration: ['p(95)<5000'],
    checks:              ['rate>0.95'],
  },
};

export default function () {
  let opened = false;
  let receivedMsg = null;

  const ws = new WebSocket(WS_URL);

  ws.addEventListener('open', () => {
    opened = true;
    // Send a JSON message on connect
    ws.send(JSON.stringify({
      ws_visitor_id: `VU_${__VU}_${Date.now()}`,
      msg: 'order_pizza',
    }));
  });

  ws.addEventListener('message', (e) => {
    try {
      receivedMsg = JSON.parse(e.data);
    } catch (_) {
      receivedMsg = { msg: e.data };
    }
    // Close after receiving the first message
    ws.close();
  });

  ws.addEventListener('error', (e) => {
    // e.error is a string property, not a method
    console.error(`WS error [VU ${__VU}]:`, e.error);
  });

  ws.addEventListener('close', () => {
    check(null, {
      'ws opened':   () => opened,
      'msg received': () => receivedMsg !== null,
    });
  });
}
