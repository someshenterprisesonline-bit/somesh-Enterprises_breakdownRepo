"""Run optional Playwright checks against synthetic temporary data, never port 8080."""
import json
import os
import subprocess

from support import AppFixture, PROJECT


def main():
    app = AppFixture()
    try:
        info = app.seed_browser()
        env = dict(os.environ, TEST_BASE_URL=app.origin, TEST_ADMIN_PIN=app.pin,
                   TEST_FIXTURE_INFO=json.dumps(info), TEST_ARTIFACT_DIR=str(app.root))
        return subprocess.call(["node", str(PROJECT / "tests/browser.cjs")], env=env)
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
