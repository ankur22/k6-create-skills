import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = 'https://quickpizza.grafana.com';

export const options = {
  vus: 5,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed:   ['rate<0.01'],
  },
};

export default function () {
  const quotesRes = http.get(`${BASE_URL}/api/quotes`);
  check(quotesRes, {
    'quotes status 200':        (r) => r.status === 200,
    'quotes body contains quotes key': (r) => r.body.includes('quotes'),
  });

  const namesRes = http.get(`${BASE_URL}/api/names`);
  check(namesRes, {
    'names status 200': (r) => r.status === 200,
  });

  sleep(1);
}
