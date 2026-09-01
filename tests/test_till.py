import json
import tempfile
import unittest
from pathlib import Path

import till


class TillResolveTargetTests(unittest.TestCase):
    def test_none_uses_cwd(self) -> None:
        cwd = Path("/tmp/work")
        self.assertEqual(till.resolve_target(None, cwd), cwd.resolve())

    def test_relative_arg_is_joined_to_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            self.assertEqual(
                till.resolve_target("my-app", cwd),
                (cwd / "my-app").resolve(),
            )


class TillConflictTests(unittest.TestCase):
    def test_empty_directory_has_no_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(till.existing_planned_paths(Path(tmp)), [])

    def test_existing_containers_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "containers.json").write_text("[]\n")
            self.assertEqual(
                till.existing_planned_paths(target),
                ["containers.json"],
            )

    def test_secrets_file_instead_of_directory_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "secrets").write_text("not a dir\n")
            self.assertIn("secrets", till.existing_planned_paths(target))


class TillWriteProjectTests(unittest.TestCase):
    def test_writes_planned_files_without_overwriting_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "demo"
            target.mkdir()
            env_src = Path(tmp) / "source.env"
            env_src.write_text(
                "GIT_AUTHOR_NAME=\n"
                "CONTAINER_USER=user\n"
                "PROJECT=project\n"
            )

            written = till.write_project(target, env_src)

            self.assertEqual(
                written,
                [
                    "containers.json",
                    ".env",
                    ".gitignore",
                    "secrets/README",
                    "secrets/ssh/README",
                ],
            )
            containers = json.loads((target / "containers.json").read_text())
            self.assertEqual(containers[0]["name"], "default")
            self.assertIn("PROJECT=demo", (target / ".env").read_text())
            self.assertTrue((target / "secrets" / "ssh" / "README").is_file())

    def test_env_fallback_when_source_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fallback"
            target.mkdir()
            content = till.env_content("fallback", Path(tmp) / "missing.env")
            self.assertIn("PROJECT=fallback", content)
            self.assertIn("CONTAINER_USER=user", content)
