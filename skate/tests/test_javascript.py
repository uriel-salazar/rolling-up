"""The JavaScript of the project has to be valid.

A file with a syntax error does not run at all: the page that loads it
loses every feature it draws with JavaScript. The check is part of the
test suite so a broken file is caught before it reaches the browser.

The check uses Node, the same program the behaviour tests of the
interface use. When Node is not installed the check is skipped.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

from django.test import SimpleTestCase

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "skate" / "static"
TESTS_DIR = PROJECT_ROOT / "skate" / "tests"


class JavaScriptSyntaxTests(SimpleTestCase):
    """Every file of JavaScript of the project has to be valid."""

    def _check(self, path):
        result = subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            "%s is not valid JavaScript:\n%s" % (path, result.stderr),
        )

    def test_the_scripts_of_the_pages_are_valid(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is not installed.")

        files = sorted(STATIC_DIR.glob("*.js"))
        self.assertTrue(files, "there are no scripts to check.")

        for path in files:
            with self.subTest(script=path.name):
                self._check(path)

    def test_the_behaviour_tests_are_valid(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is not installed.")

        files = sorted(TESTS_DIR.glob("*.test.js"))
        self.assertTrue(files, "there are no behaviour tests to check.")

        for path in files:
            with self.subTest(script=path.name):
                self._check(path)
