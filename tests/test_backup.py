import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import backup


class SecretsHaveRealContentTests(unittest.TestCase):
    def test_only_placeholders_returns_false(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            secrets = Path(tmp) / "secrets"
            (secrets / "ssh").mkdir(parents=True)
            (secrets / "README").write_text("placeholder\n")
            (secrets / "ssh" / "README").write_text("placeholder\n")

            self.assertFalse(backup.secrets_have_real_content(secrets))

    def test_extra_top_level_file_returns_true(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            secrets = Path(tmp) / "secrets"
            secrets.mkdir()
            (secrets / "token.txt").write_text("secret\n")

            self.assertTrue(backup.secrets_have_real_content(secrets))

    def test_extra_nested_file_under_ssh_returns_true(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            secrets = Path(tmp) / "secrets"
            (secrets / "ssh").mkdir(parents=True)
            (secrets / "ssh" / "id_ed25519").write_text("secret\n")

            self.assertTrue(backup.secrets_have_real_content(secrets))

    def test_empty_directory_returns_false(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            secrets = Path(tmp) / "secrets"
            (secrets / "ssh").mkdir(parents=True)

            self.assertFalse(backup.secrets_have_real_content(secrets))


class StripProjectVolumeSuffixTests(unittest.TestCase):
    def test_strips_project_prefix(self) -> None:
        self.assertEqual(
            backup.strip_project_volume_suffix("demo_root", "demo"),
            "root",
        )


class DefaultBackupPathTests(unittest.TestCase):
    def test_builds_project_timestamped_filename(self) -> None:
        now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        path = backup.default_backup_path(Path("/work/project"), "demo", now)

        self.assertEqual(
            path,
            Path("/work/project/demo-backup-20260102030405.tar"),
        )


class BuildBackupManifestTests(unittest.TestCase):
    def test_builds_restore_contract_manifest(self) -> None:
        created_at = datetime(2026, 9, 28, 11, 44, 1, tzinfo=timezone.utc)

        manifest = backup.build_backup_manifest(
            project_name="demo",
            created_at=created_at,
            volumes=["root", "cache"],
            included_secrets=True,
        )

        self.assertEqual(
            manifest,
            {
                "format_version": 1,
                "project_name": "demo",
                "created_at": "2026-09-28T11:44:01Z",
                "volumes": ["root", "cache"],
                "included_secrets": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
