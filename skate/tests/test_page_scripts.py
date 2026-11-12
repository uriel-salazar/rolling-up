"""The order of the markup and of the scripts of the pages.

A script of a page runs when the browser reaches it, so it can only use
the markup that was already read. When a script looks for an element
that comes after it in the page, the element does not exist yet, the
script stops with an error and the page stays empty.

These tests check that every element a script looks for is in the page
before the script runs. They protect the pages of the application from
that mistake, which is silent: the page is served, the answer is a 200
and nothing happens on the screen.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set

from django.test import SimpleTestCase

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "skate" / "templates"
STATIC_DIR = PROJECT_ROOT / "skate" / "static"


def elements_looked_for(script: str) -> Set[str]:
    """Return the ids the script looks for in the page."""
    return set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", script))


def ids_defined_in(template: str) -> Dict[str, int]:
    """Return the line of every id the template defines."""
    found: Dict[str, int] = {}
    for number, line in enumerate(template.split("\n"), start=1):
        for identifier in re.findall(r'id="([^"]+)"', line):
            found.setdefault(identifier, number)
    return found


def script_lines(template: str) -> List[int]:
    """Return the line of every script of the template."""
    return [
        number
        for number, line in enumerate(template.split("\n"), start=1)
        if "<script src=" in line
    ]


class TemplateScriptOrderTests(SimpleTestCase):
    """The scripts of the pages have to run after their markup."""

    def _check(self, template_name: str):
        template = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")

        defined = ids_defined_in(template)
        scripts = script_lines(template)
        if not scripts:
            return

        last_script = max(scripts)

        for script_path in sorted(STATIC_DIR.glob("*.js")):
            script = script_path.read_text(encoding="utf-8")
            wanted = elements_looked_for(script)
            if not wanted:
                continue

            too_late = sorted(
                identifier
                for identifier in wanted
                if identifier in defined and defined[identifier] > last_script
            )

            self.assertEqual(
                too_late,
                [],
                "%s looks for %s, but they are defined after the last "
                "script of %s. The script stops with an error and the page "
                "stays empty."
                % (
                    script_path.name,
                    ", ".join(too_late),
                    template_name,
                ),
            )

    def test_the_page_of_the_feed(self):
        self._check("feed.html")

    def test_the_page_of_the_map(self):
        self._check("map.html")

    def test_the_page_of_the_spot(self):
        self._check("spot_detail.html")

    def test_the_page_of_the_form(self):
        self._check("spot_form.html")

    def test_the_page_of_the_profile(self):
        self._check("profile.html")

    def test_the_page_of_the_register(self):
        self._check("register.html")

    def test_the_page_of_the_home(self):
        self._check("basic_home.html")


class HiddenAttributeTests(SimpleTestCase):
    """The attribute "hidden" has to hide the element.

    The browser hides the elements with the attribute, but any rule of
    the application that sets a "display" wins over the rule of the
    browser, and the element stays on the screen. The application needs
    a rule of its own for that.
    """

    def test_the_stylesheet_hides_the_hidden_elements(self):
        stylesheet = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

        self.assertIn(
            "[hidden]",
            stylesheet,
            "The stylesheet needs a rule for the attribute 'hidden', "
            "otherwise the elements the scripts hide stay on the screen.",
        )

        rule = re.search(r"(?m)^\[hidden\]\s*\{([^}]*)\}", stylesheet)
        self.assertIsNotNone(rule, "the rule of the attribute 'hidden' is missing")
        self.assertIn("display", rule.group(1))
        self.assertIn("none", rule.group(1))


class ScriptGlobalTests(SimpleTestCase):
    """The scripts have to use the names the browser knows.

    ``global`` is a name of Node.js, the browser does not have it. A
    script that uses it stops with an error.
    """

    def test_the_scripts_do_not_use_the_name_of_node(self):
        for script_path in sorted(STATIC_DIR.glob("*.js")):
            script = script_path.read_text(encoding="utf-8")

            # ``global`` is fine when it is the parameter of the
            # function, the browser is then given the window.
            uses = re.findall(r"(?<![\w.])global(?![\w])", script)
            if not uses:
                continue

            takes_global = re.search(
                r"function\s*\(\s*global\s*\)", script
            )
            self.assertIsNotNone(
                takes_global,
                "%s uses 'global' but does not receive it as a parameter. "
                "The browser does not have that name and the script stops "
                "with an error." % script_path.name,
            )
