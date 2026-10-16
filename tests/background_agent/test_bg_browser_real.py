"""Integration test against a real headless Chromium. Auto-skips if Playwright/Chromium
are unavailable. Uses only a local 127.0.0.1 HTTP server (no internet)."""
import http.server
import tempfile
import threading
import time
import unittest
from pathlib import Path

import helpers  # noqa: F401
from background_agent import Action, ActionKind, CancelToken
from background_agent.backends.browser import BrowserUnavailable, PlaywrightEngine
from background_agent.backends.local_tools import LocalToolBackend

PAGE = b"<html><title>Fixture</title><body><h1>Hello Ruby</h1><button id=b onclick=\"this.textContent='clicked'\">go</button></body></html>"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *a):
        pass


class RealChromiumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            probe = PlaywrightEngine()
            probe.close()
        except BrowserUnavailable as exc:
            raise unittest.SkipTest(f"real Chromium unavailable: {str(exc)[:100]}")
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_real_browser_through_the_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = LocalToolBackend(Path(tmp), enable_browser=True, cleanup_timeout=20).open_environment("t")
            try:
                def do(kind, **p):
                    return env.execute(Action(kind, p), deadline=time.monotonic() + 40, cancel=CancelToken())
                r = do(ActionKind.BROWSER_GOTO, url=self.url)
                self.assertTrue(r.ok, r.error)
                self.assertIn("Fixture", r.output)
                self.assertEqual(do(ActionKind.BROWSER_EXTRACT_TEXT, selector="h1").output, "Hello Ruby")
                self.assertTrue(do(ActionKind.BROWSER_CLICK, selector="#b").ok)
                self.assertEqual(do(ActionKind.BROWSER_EXTRACT_TEXT, selector="#b").output, "clicked")
                shot = do(ActionKind.BROWSER_SCREENSHOT, path="shots/page.png")
                self.assertTrue(shot.ok, shot.error)
                self.assertGreater(Path(shot.produced_paths[0]).stat().st_size, 1000)
                self.assertFalse(do(ActionKind.BROWSER_CLICK, selector="#does-not-exist", timeout_seconds=1).ok)
            finally:
                env.close()  # must shut Chromium down on the browser's own thread


if __name__ == "__main__":
    unittest.main()
