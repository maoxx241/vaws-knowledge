from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from knowledge_intake.common import Budget, ImportLimit, IntakeError, Limits, command
from knowledge_intake.sources import _gh_path, _url_bytes, github_api


class SourceRuntimeTests(unittest.TestCase):
    def test_real_gh_without_auth_uses_public_http_with_same_budget(self):
        gh = _gh_path()
        if gh is None:
            self.skipTest("GitHub CLI unavailable")
        payload = b'{"sha":"public-fixture"}'
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append((self.path, self.headers.get("Authorization")))
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as config:
                # An isolated empty gh config models a scheduler without client auth.
                # Do not inspect, change or copy the signed-in user's credentials.
                env = {key: value for key, value in os.environ.items() if key not in
                       {"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"}}
                env["GH_CONFIG_DIR"] = config
                with patch.dict(os.environ, env, clear=True):
                    result = subprocess.run([gh, "api", "repos/example/public"], capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 4)
                    budget = Budget(Limits(seconds=20))

                    def public(url, same_budget):
                        self.assertEqual(url, "https://api.github.com/repos/example/public")
                        self.assertIs(same_budget, budget)
                        return _url_bytes(f"http://127.0.0.1:{server.server_port}/public", same_budget)

                    with patch("knowledge_intake.sources._url_bytes", side_effect=public):
                        self.assertEqual(github_api("repos/example/public", budget), json.loads(payload))
                    self.assertEqual(budget.bytes, len(payload))
                    self.assertEqual(calls, [("/public", None)])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_gh_non_auth_errors_are_not_retried_anonymously(self):
        for code in (1, 2):
            with self.subTest(code=code), patch("knowledge_intake.sources._gh_path", return_value="gh"), \
                    patch("knowledge_intake.sources.command", return_value=(code, b"")), \
                    patch("knowledge_intake.sources._url_bytes", side_effect=AssertionError("unexpected fallback")):
                with self.assertRaisesRegex(IntakeError, f"exit {code}"):
                    github_api("repos/example/public", Budget(Limits()))

    def test_parent_memory_sampling_stops_a_real_child(self):
        observed = []

        def over_budget(pid):
            observed.append(pid)
            return 513 * 1024 * 1024

        with patch("knowledge_intake.common.sys.platform", "darwin"), \
                patch("knowledge_intake.common._darwin_rss_reader", return_value=over_budget):
            with self.assertRaisesRegex(ImportLimit, "resident memory"):
                command([sys.executable, "-c", "import time; time.sleep(30)"],
                        timeout=5, max_bytes=4096, memory_mb=512)
        self.assertEqual(len(observed), 1)

    @unittest.skipUnless(sys.platform == "darwin", "native macOS libproc acceptance")
    def test_native_darwin_resident_memory_budget(self):
        _, result = command([sys.executable, "-c", "import time; print('small'); time.sleep(.1)"],
                            timeout=10, max_bytes=4096, memory_mb=512)
        self.assertEqual(result.strip(), b"small")
        with self.assertRaisesRegex(ImportLimit, "resident memory"):
            command([sys.executable, "-c", "import time; allocation=bytearray(128*1024*1024); time.sleep(10)"],
                    timeout=5, max_bytes=4096, memory_mb=64)


if __name__ == "__main__":
    unittest.main()
