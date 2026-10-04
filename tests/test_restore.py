import json
import tempfile
import unittest
from pathlib import Path

import restore


class NormalizeProjectNameTests(unittest.TestCase):
    def test_lowercases_valid_name(self) -> None:
        self.assertEqual(restore.normalize_project_name("MyProj"), "myproj")

    def test_rejects_invalid_first_character(self) -> None:
        with self.assertRaises(restore.RestoreError):
            restore.normalize_project_name("-bad")

    def test_rejects_invalid_characters(self) -> None:
        with self.assertRaises(restore.RestoreError):
            restore.normalize_project_name("bad name")


class ResolveTargetTests(unittest.TestCase):
    def test_defaults_to_cwd_when_arg_missing(self) -> None:
        cwd = Path("/tmp/somewhere")
        self.assertEqual(restore.resolve_target(None, cwd), cwd.resolve())

    def test_relative_arg_resolved_against_cwd(self) -> None:
        cwd = Path("/tmp/somewhere")
        self.assertEqual(restore.resolve_target("child", cwd), (cwd / "child").resolve())

    def test_absolute_arg_used_as_is(self) -> None:
        cwd = Path("/tmp/somewhere")
        self.assertEqual(restore.resolve_target("/abs/path", cwd), Path("/abs/path").resolve())


class LoadManifestTests(unittest.TestCase):
    def test_loads_valid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            extract_dir = Path(tmp)
            metadata = extract_dir / "metadata"
            metadata.mkdir()
            manifest = {
                "format_version": 1,
                "project_name": "demo",
                "created_at": "2024-01-01T00:00:00Z",
                "volumes": ["root"],
                "included_secrets": False,
            }
            (metadata / "backup.json").write_text(json.dumps(manifest))
            loaded = restore.load_manifest(extract_dir)
            self.assertEqual(loaded["project_name"], "demo")

    def test_missing_manifest_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(restore.RestoreError):
                restore.load_manifest(Path(tmp))

    def test_unsupported_format_version_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            extract_dir = Path(tmp)
            metadata = extract_dir / "metadata"
            metadata.mkdir()
            (metadata / "backup.json").write_text(json.dumps({"format_version": 99}))
            with self.assertRaises(restore.RestoreError):
                restore.load_manifest(extract_dir)


class RewriteComposeProjectNameTests(unittest.TestCase):
    def test_adds_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("FOO=bar\n")
            restore.rewrite_compose_project_name(env_path, "newname")
            content = env_path.read_text()
            self.assertIn("FOO=bar\n", content)
            self.assertIn("COMPOSE_PROJECT_NAME=newname\n", content)

    def test_replaces_existing_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("COMPOSE_PROJECT_NAME=old\nFOO=bar\n")
            restore.rewrite_compose_project_name(env_path, "newname")
            content = env_path.read_text()
            self.assertEqual(content, "COMPOSE_PROJECT_NAME=newname\nFOO=bar\n")

    def test_missing_env_file_creates_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            restore.rewrite_compose_project_name(env_path, "newname")
            self.assertEqual(env_path.read_text(), "COMPOSE_PROJECT_NAME=newname\n")


class SnapshotRestoreTests(unittest.TestCase):
    def test_file_snapshot_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.txt"
            path.write_text("original")
            snapshot = restore.snapshot_path(path)
            path.write_text("overwritten")
            restore.restore_snapshot(path, snapshot)
            self.assertEqual(path.read_text(), "original")

    def test_missing_path_snapshot_is_none_and_restore_removes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.txt"
            snapshot = restore.snapshot_path(path)
            self.assertIsNone(snapshot)
            path.write_text("new content")
            restore.restore_snapshot(path, snapshot)
            self.assertFalse(path.exists())

    def test_directory_snapshot_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dir"
            path.mkdir()
            (path / "a.txt").write_text("original")
            snapshot = restore.snapshot_path(path)
            (path / "a.txt").write_text("overwritten")
            (path / "b.txt").write_text("extra")
            restore.restore_snapshot(path, snapshot)
            self.assertEqual((path / "a.txt").read_text(), "original")
            self.assertFalse((path / "b.txt").exists())


class RollbackLedgerTests(unittest.TestCase):
    def test_rolls_back_in_reverse_order(self) -> None:
        order: list[int] = []
        ledger = restore.RollbackLedger()
        ledger.append("first", lambda: order.append(1))
        ledger.append("second", lambda: order.append(2))
        ledger.append("third", lambda: order.append(3))
        failures = ledger.rollback()
        self.assertEqual(order, [3, 2, 1])
        self.assertEqual(failures, [])

    def test_collects_undo_failures_and_keeps_going(self) -> None:
        order: list[str] = []

        def boom() -> None:
            raise RuntimeError("nope")

        ledger = restore.RollbackLedger()
        ledger.append("ok-1", lambda: order.append("ok-1"))
        ledger.append("boom", boom)
        ledger.append("ok-2", lambda: order.append("ok-2"))
        failures = ledger.rollback()
        self.assertEqual(order, ["ok-2", "ok-1"])
        self.assertEqual(len(failures), 1)
        self.assertIn("boom", failures[0])


if __name__ == "__main__":
    unittest.main()
