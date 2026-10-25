import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import ds


class DsAddTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self._cwd = Path.cwd()
        os.chdir(self.project)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _add(self, *args: str) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ds.add(list(args))
        return out.getvalue()

    def _names(self) -> list[str]:
        return [c["name"] for c in json.loads((self.project / "containers.json").read_text())]

    def test_no_argument_lists_recipes(self) -> None:
        self.assertIn("ollama", self._add().split())

    def test_appends_recipe_services_and_keeps_layout(self) -> None:
        (self.project / "containers.json").write_text('[\n    {"name": "default"}\n]\n')
        self._add("ollama")
        self.assertEqual(self._names(), ["default", "ollama", "ollama_chat"])
        self.assertIn('"templates": ["ollama"]', (self.project / "containers.json").read_text())

    def test_empty_containers_json(self) -> None:
        (self.project / "containers.json").write_text("[]\n")
        self._add("python")
        self.assertEqual(self._names(), ["python"])

    def test_existing_service_name_stops_without_writing(self) -> None:
        original = '[\n    {"name": "ollama_chat"}\n]\n'
        (self.project / "containers.json").write_text(original)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self._add("ollama")
        self.assertEqual((self.project / "containers.json").read_text(), original)

    def test_unknown_recipe_fails(self) -> None:
        (self.project / "containers.json").write_text("[]\n")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self._add("no-such-recipe")

    def test_missing_containers_json_fails(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self._add("python")


class DsAddTemplateTests(unittest.TestCase):
    CONTAINERS = """[
    {
        "name": "@base",
        "templates": ["git"]
    },
    {
        "name": "app",
        "enabled": true,
        "cmd": ["/bin/bash"]
    },
    {"name": "inline", "templates": []},
    {
        "name": "multi",
        "templates": [
            "python"
        ]
    },
    {"name": "child", "extends": "app"}
]
"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.file = self.project / "containers.json"
        self.file.write_text(self.CONTAINERS)
        self._cwd = Path.cwd()
        os.chdir(self.project)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _add(self, *args: str) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ds.add_template(list(args))
        return out.getvalue()

    def _fails(self, *args: str) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self._add(*args)
        self.assertEqual(self.file.read_text(), self.CONTAINERS)

    def _templates(self, name: str) -> list[str]:
        containers = json.loads(self.file.read_text())
        return next(c for c in containers if c["name"] == name).get("templates")

    def test_creates_templates_after_enabled(self) -> None:
        self._add("app", "@base")
        self.assertEqual(self._templates("app"), ["@base"])
        self.assertIn('"enabled": true,\n        "templates": ["@base"],\n', self.file.read_text())

    def test_inserts_before_last_in_inline_and_multiline_lists(self) -> None:
        self._add("inline", "node")
        self._add("inline", "git")
        self._add("multi", "service:app")
        self.assertEqual(self._templates("inline"), ["git", "node"])
        self.assertEqual(self._templates("multi"), ["service:app", "python"])
        self.assertIn('{"name": "inline", "templates": ["git", "node"]}', self.file.read_text())
        self.assertIn('[\n            "service:app",\n            "python"\n', self.file.read_text())
        self._add("inline", "@base")
        self.assertEqual(self._templates("inline"), ["git", "@base", "node"])

    def test_lists_services_and_references(self) -> None:
        self.assertEqual(self._add().split(), ["@base", "app", "inline", "multi"])
        choices = self._add("app").split()
        self.assertIn("git", choices)
        self.assertIn("@base", choices)
        self.assertIn("service:multi", choices)
        self.assertNotIn("service:app", choices)

    def test_rejects_extending_service(self) -> None:
        self._fails("child", "git")

    def test_rejects_unknown_references(self) -> None:
        self._fails("app", "no-such-template")
        self._fails("app", "@missing")
        self._fails("app", "service:missing")
        self._fails("app", "other:git")

    def test_rejects_duplicates_in_either_spelling(self) -> None:
        self._fails("multi", "python")
        self._fails("@base", "git")
        self._add("app", "@base")
        before = self.file.read_text()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self._add("app", "service:@base")
        self.assertEqual(self.file.read_text(), before)

    def test_rejects_cycles(self) -> None:
        self._fails("app", "service:app")
        self._fails("app", "service:child")
        self._add("multi", "@base")
        before = self.file.read_text()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self._add("@base", "service:multi")
        self.assertEqual(self.file.read_text(), before)


class DsExtendTests(unittest.TestCase):
    CONTAINERS = """[
    {"name": "@base", "templates": ["git"]},
    {
        "name": "app",
        "enabled": true,
        "templates": ["python", "@base"]
    }
]
"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.file = self.project / "containers.json"
        self.file.write_text(self.CONTAINERS)
        self._cwd = Path.cwd()
        os.chdir(self.project)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _extend(self, *args: str) -> tuple[str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            ds.extend(list(args))
        return out.getvalue(), err.getvalue()

    def _fails(self, *args: str) -> None:
        with self.assertRaises(SystemExit):
            self._extend(*args)
        self.assertEqual(self.file.read_text(), self.CONTAINERS)

    def _entry(self, name: str) -> dict:
        return next(c for c in json.loads(self.file.read_text()) if c["name"] == name)

    def test_main_defaults_to_new_service_name(self) -> None:
        _, err = self._extend("app", "python")
        self.assertEqual(
            self._entry("python"),
            {"name": "python", "enabled": True, "extends": "app", "main": "python"},
        )
        self.assertEqual(err, "")

    def test_explicit_template_from_abstract_reference(self) -> None:
        _, err = self._extend("app", "git_shell", "git")
        self.assertEqual(self._entry("git_shell")["main"], "git")
        self.assertEqual(err, "")

    def test_warns_when_template_is_not_in_parent_image(self) -> None:
        _, err = self._extend("app", "web", "node")
        self.assertEqual(self._entry("web")["main"], "node")
        self.assertIn("not built into", err)

    def test_command_is_split_into_cmd(self) -> None:
        self._extend("app", "repl", "--command", "python -c 'print(1)'")
        self._extend("app", "sh", "--command=bash -l")
        self.assertEqual(self._entry("repl")["cmd"], ["python", "-c", "print(1)"])
        self.assertNotIn("main", self._entry("repl"))
        self.assertEqual(self._entry("sh")["cmd"], ["bash", "-l"])

    def test_lists_services_and_parent_templates(self) -> None:
        self.assertEqual(self._extend()[0].split(), ["app"])
        self.assertIn("git", self._extend("app")[0].split())
        self.assertIn("python", self._extend("app")[0].split())

    def test_rejects_bad_input(self) -> None:
        self._fails("missing", "x", "git")
        self._fails("@base", "x", "git")
        self._fails("app", "app", "git")
        self._fails("app", "bad-name", "git")
        self._fails("app", "x", "no-such-template")
        self._fails("app", "x", "git", "--command", "bash")
        self._fails("app", "x", "--command", "")
        self._fails("app", "x", "--command")


class DsNewTests(unittest.TestCase):
    CONTAINERS = """[
    {"name": "@base", "templates": ["git"]},
    {
        "name": "app",
        "enabled": true,
        "templates": ["python", "@base"]
    }
]
"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.file = self.project / "containers.json"
        self.file.write_text(self.CONTAINERS)
        self._cwd = Path.cwd()
        os.chdir(self.project)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _new(self, *args: str) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ds.new(list(args))
        return out.getvalue()

    def _fails(self, *args: str) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self._new(*args)
        self.assertEqual(self.file.read_text(), self.CONTAINERS)

    def _entry(self, name: str) -> dict:
        return next(c for c in json.loads(self.file.read_text()) if c["name"] == name)

    def test_empty_service(self) -> None:
        self._new("web")
        self.assertEqual(self._entry("web"), {"name": "web", "enabled": True, "templates": []})
        self.assertTrue(self.file.read_text().startswith(self.CONTAINERS.rstrip()[:-1].rstrip()))

    def test_references_in_order(self) -> None:
        self._new("web", "node", "@base", "service:app")
        self.assertEqual(self._entry("web")["templates"], ["node", "@base", "service:app"])

    def test_abstract_service_has_no_enabled(self) -> None:
        self._new("@tools", "git")
        self.assertEqual(self._entry("@tools"), {"name": "@tools", "templates": ["git"]})

    def test_lists_references(self) -> None:
        choices = self._new().split()
        self.assertIn("git", choices)
        self.assertIn("@base", choices)
        self.assertIn("service:app", choices)

    def test_rejects_bad_input(self) -> None:
        self._fails("app")
        self._fails("@base")
        self._fails("bad-name")
        self._fails("web", "no-such-template")
        self._fails("web", "service:missing")
        self._fails("web", "service:web")
        self._fails("web", "git", "git")
        self._fails("web", "@base", "service:@base")


if __name__ == "__main__":
    unittest.main()


class DsScriptTests(unittest.TestCase):
    def test_every_script_has_main(self) -> None:
        for name in ds.SCRIPTS:
            self.assertTrue((ds.REPO_DIR / f"{name}.py").is_file(), name)
            self.assertTrue(callable(importlib.import_module(name).main), name)

    def test_dispatches_with_ds_prefixed_argv(self) -> None:
        argv = sys.argv
        err = io.StringIO()
        try:
            sys.argv = ["ds", "configure", "a", "b"]
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                ds.main()
        finally:
            sys.argv = argv
        self.assertIn("Usage: ds configure [.env]", err.getvalue())

    def test_help_lists_every_command(self) -> None:
        argv = sys.argv
        out = io.StringIO()
        try:
            sys.argv = ["ds", "--help"]
            with contextlib.redirect_stdout(out):
                ds.main()
        finally:
            sys.argv = argv
        commands = {*ds.SCRIPTS, *ds.ACTIONS, "shell", "list", "add", "add-template", "new", "extend"}
        for command in commands:
            self.assertIn(f"    ds {command} ", out.getvalue().replace("ds up  ", "ds up "), command)
