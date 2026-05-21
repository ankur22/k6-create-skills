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


if __name__ == "__main__":
    unittest.main()
