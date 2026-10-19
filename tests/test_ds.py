import contextlib
import io
import json
import os
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




if __name__ == "__main__":
    unittest.main()
