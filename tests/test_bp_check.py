import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scenario-manifest.json"

spec = importlib.util.spec_from_file_location("bp_check", ROOT / "bp-check.py")
bp_check = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bp_check)


class BestPracticeCheckerTest(unittest.TestCase):
    def write_script(self, directory: Path, relpath: str, content: str) -> Path:
        path = directory / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_options_alone_is_not_an_exported_test_function(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self.write_script(Path(tmp), "script.js", "export const options = {};\n")
            result = bp_check.score(str(script))

        self.assertIn("R10 exported test function(s)", result["issues"])

    def test_comments_do_not_satisfy_assertion_rule(self):
        code = """
import http from 'k6/http';
export const options = { vus: 1, duration: '1s', thresholds: { http_req_duration: ['p(95)<500'] } };
export default function () {
  // check(res, { 'status 200': r => r.status === 200 });
  http.get('https://quickpizza.grafana.com/api/quotes');
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            script = self.write_script(Path(tmp), "script.js", code)
            result = bp_check.score(str(script))

        self.assertIn("R3 assertions (check/expect)", result["issues"])

    def test_grpc_close_must_be_in_finally(self):
        code = """
import { Client, StatusOK } from 'k6/net/grpc';
import { check, sleep } from 'k6';
const client = new Client();
client.load(['./proto'], 'quickpizza.proto');
export const options = { vus: 3, duration: '20s', thresholds: { grpc_req_duration: ['p(95)<500'] } };
export default function () {
  client.connect('localhost:3334', { plaintext: true });
  const res = client.invoke('quickpizza.GRPC/Status', {});
  check(res, { 'ok': r => r.status === StatusOK });
  client.close();
  sleep(1);
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            script = self.write_script(Path(tmp), "k6/scripts/quickpizza-grpc.js", code)
            result = bp_check.score(str(script), scenario="5", manifest_path=str(MANIFEST), result_dir=tmp)

        self.assertIn("P6 gRPC client.close() in finally", result["issues"])

    def test_browser_manifest_requires_enough_screenshots(self):
        code = """
import { expect } from 'https://jslib.k6.io/k6-testing/0.6.1/index.js';
import { browser } from 'k6/browser';
export const options = { scenarios: { functional: { executor: 'shared-iterations', vus: 1, iterations: 1, options: { browser: { type: 'chromium' } } } } };
export default async function () {
  const page = await browser.newPage();
  try {
    await page.goto('https://quickpizza.grafana.com');
    await page.screenshot({ path: 'screenshots/01.png' });
    await page.getByRole('link', { name: 'Login' }).click();
    await page.locator('#username').fill('default');
    await page.locator('#password').fill('12345678');
    await page.getByRole('link', { name: 'Back to main page' }).click();
    await page.getByRole('button', { name: 'Pizza, Please!' }).click();
    await page.getByRole('button', { name: 'Love it!' }).click();
    await expect(page.getByText('Rated!')).toBeVisible();
  } finally {
    await page.close();
  }
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            script = self.write_script(Path(tmp), "k6/scripts/quickpizza-functional.js", code)
            result = bp_check.score(str(script), scenario="19", manifest_path=str(MANIFEST), result_dir=tmp)

        self.assertTrue(any(issue.startswith("S19.screenshots") for issue in result["issues"]))

    def test_missing_script_scores_visible_failure(self):
        result = bp_check.score(None, scenario="27", manifest_path=str(MANIFEST))

        self.assertEqual(result["score"], 0)
        self.assertEqual(result["max"], 1)
        self.assertIn("script file exists", result["issues"])

    def test_http_request_matches_const_url_pattern(self):
        # S18 pattern: URL stored in const, then http.post(url) called.
        code = """
import http from 'k6/http';
import { check } from 'k6';
export const options = {
  cloud: { projectID: 1234567, name: 'QuickPizza Hybrid Test' },
  scenarios: {
    pizza_api: {
      executor: 'constant-arrival-rate',
      rate: 15,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 30,
      maxVUs: 100,
    },
  },
};
export default function () {
  const url = 'https://quickpizza.grafana.com/api/pizza';
  const params = { headers: { 'Authorization': 'Token abc1234567890123' } };
  const res = http.post(url, null, params);
  check(res, { 'status 200': r => r.status === 200 });
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            script = self.write_script(Path(tmp), "k6/scripts/quickpizza-cloud-local-exec.js", code)
            result = bp_check.score(str(script), scenario="18", manifest_path=str(MANIFEST), result_dir=tmp)

        pizza_issue = [i for i in result["issues"] if "pizza_post" in i]
        self.assertEqual(pizza_issue, [], f"unexpected issue for const-URL pattern: {result['issues']}")

    def test_raw_target_finds_content_inside_comments(self):
        # S17.run_comment lives in a comment header; raw-target rules see it.
        code = """// QuickPizza Cloud Load Test
// How to run:
//   k6 cloud login --token <TOKEN>
//   k6 cloud run script.js
import http from 'k6/http';
import { check, sleep } from 'k6';
export const options = {
  cloud: {
    projectID: 1234567,
    name: 'QuickPizza Cloud Load Test',
    distribution: {
      ash: { loadZone: 'amazon:us:ashburn', percent: 60 },
      dub: { loadZone: 'amazon:eu:dublin', percent: 40 },
    },
  },
  scenarios: {
    load_test: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },
        { duration: '5m', target: 50 },
        { duration: '1m', target: 0 },
      ],
    },
  },
  thresholds: { http_req_duration: ['p(95)<500'] },
};
export default function () {
  const res = http.get('https://quickpizza.grafana.com/api/quotes');
  check(res, { 'status 200': r => r.status === 200 });
  sleep(1);
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            script = self.write_script(Path(tmp), "k6/scripts/quickpizza-cloud.js", code)
            result = bp_check.score(str(script), scenario="17", manifest_path=str(MANIFEST), result_dir=tmp)

        comment_issue = [i for i in result["issues"] if "run_comment" in i]
        self.assertEqual(comment_issue, [], f"raw-target rule should see comment text: {result['issues']}")

    def test_execution_module_alias_is_flexible(self):
        # S10: prompt suggests `import execution from 'k6/execution'` but mcp-k6
        # chose alias `exec`. Manifest should accept either.
        code = """
import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';
export const options = {
  scenarios: {
    per_vu: {
      executor: 'per-vu-iterations',
      vus: 5,
      iterations: 3,
      maxDuration: '2m',
    },
  },
};
export default function () {
  const vuId = exec.vu.idInTest;
  const iter = exec.scenario.iterationInInstance;
  const res = http.get('https://quickpizza.grafana.com/api/quotes', { tags: { vu: String(vuId) } });
  check(res, { 'status 200': r => r.status === 200 });
}
export function handleSummary(data) {
  return { stdout: 'done' };
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            script = self.write_script(Path(tmp), "k6/scripts/quickpizza-execution-summary.js", code)
            result = bp_check.score(str(script), scenario="10", manifest_path=str(MANIFEST), result_dir=tmp)

        adherence = result["categories"].get("prompt_adherence", {})
        bad = [i for i in adherence.get("issues", []) if "vu_id" in i or "iter_in_instance" in i]
        self.assertEqual(bad, [], f"alias-flexible checks should pass: {adherence}")


if __name__ == "__main__":
    unittest.main()
