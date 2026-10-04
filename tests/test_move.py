import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import move


class MoveArgumentsAndPathsTests(unittest.TestCase):
    def test_requires_project_and_target_arguments(self) -> None:
        with self.assertRaises(SystemExit):
            move.parse_args(["./project"])

    def test_parses_project_target_and_force(self) -> None:
        self.assertEqual(
            move.parse_args(["./project", "../newplace/newname", "--force"]),
            ("./project", "../newplace/newname", True),
        )

    def test_trailing_slash_places_project_inside_existing_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "demo"
            project.mkdir()
            target_dir = root / "destination"
            target_dir.mkdir()

            target = move.resolve_target(project, f"{target_dir}/")

            self.assertEqual(target, target_dir / "demo")

    def test_target_without_trailing_slash_is_exact_destination(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "demo"
            project.mkdir()
            destination = root / "renamed"

            self.assertEqual(move.resolve_target(project, str(destination)), destination)

    def test_rejects_existing_final_destination(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "demo"
            project.mkdir()
            destination = root / "renamed"
            destination.mkdir()

            with self.assertRaisesRegex(move.MoveError, "Target already exists"):
                move.resolve_target(project, str(destination))

    def test_rejects_existing_dangling_symlink_destination(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "demo"
            project.mkdir()
            destination = root / "renamed"
            destination.symlink_to(root / "missing")

            with self.assertRaisesRegex(move.MoveError, "Target already exists"):
                move.resolve_target(project, str(destination))

    def test_requires_containers_json_for_project(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "not-a-project"
            project.mkdir()

            with self.assertRaisesRegex(move.MoveError, "missing containers.json"):
                move.resolve_project_directory(str(project))

    def test_preflight_preserves_identity_when_target_is_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "demo"
            project.mkdir()
            (project / "containers.json").write_text("[]\n")
            (project / ".env").write_text("COMPOSE_PROJECT_NAME=custom-name\n")
            destination = root / "destination"
            destination.mkdir()

            result = move.preflight(False, str(project), f"{destination}/")

            self.assertEqual(
                result,
                (
                    "custom-name",
                    "custom-name",
                    project,
                    destination / "demo",
                    False,
                ),
            )

    def test_preflight_detects_new_identity_for_exact_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "demo"
            project.mkdir()
            (project / "containers.json").write_text("[]\n")
            destination = root / "renamed"

            with (
                patch.object(move, "require_docker"),
                patch.object(move, "check_docker_daemon"),
                patch.object(move, "list_running_project_containers", return_value=[]),
                patch.object(move, "list_project_volumes", return_value=[]),
                patch.object(move, "list_project_images", return_value=[]),
            ):
                result = move.preflight(False, str(project), str(destination))

            self.assertEqual(result, ("demo", "renamed", project, destination, True))

    def test_force_does_not_allow_existing_final_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "demo"
            project.mkdir()
            (project / "containers.json").write_text("[]\n")
            destination = root / "renamed"
            destination.mkdir()

            with patch.object(move, "require_docker") as require_docker:
                with self.assertRaises(SystemExit):
                    move.preflight(True, str(project), str(destination))

            require_docker.assert_not_called()

    def test_directory_only_move_preserves_project_files_and_skips_docker(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "demo"
            project.mkdir()
            (project / "containers.json").write_text("[]\n")
            (project / ".env").write_text("COMPOSE_PROJECT_NAME=demo\n")
            destination = root / "parent" / "demo"
            destination.parent.mkdir()

            with patch.object(move, "run_docker") as run_docker:
                move.move_project("demo", "demo", project, destination, False)

            self.assertFalse(project.exists())
            self.assertTrue((destination / "containers.json").is_file())
            self.assertEqual(
                (destination / ".env").read_text(),
                "COMPOSE_PROJECT_NAME=demo\n",
            )
            run_docker.assert_not_called()

    def test_name_change_updates_env_and_moves_project(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "demo"
            project.mkdir()
            (project / "containers.json").write_text("[]\n")
            (project / ".env").write_text("COMPOSE_PROJECT_NAME=demo\n")
            destination = root / "renamed"

            with (
                patch.object(move, "list_project_volumes", return_value=[]),
                patch.object(move, "list_project_images", return_value=[]),
            ):
                move.move_project("demo", "renamed", project, destination, True)

            self.assertFalse(project.exists())
            self.assertEqual(
                (destination / ".env").read_text(),
                "COMPOSE_PROJECT_NAME=renamed\n",
            )


class NormalizeProjectNameTests(unittest.TestCase):
    def test_lowercases_valid_name(self) -> None:
        self.assertEqual(move.normalize_project_name("My.Project-01"), "my.project-01")

    def test_rejects_empty_name(self) -> None:
        with self.assertRaises(ValueError):
            move.normalize_project_name("")

    def test_rejects_invalid_first_character(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            move.normalize_project_name("-oops")
        self.assertIn("'-oops'", str(ctx.exception))

    def test_rejects_invalid_characters(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            move.normalize_project_name("Bad Name")
        self.assertIn("'bad name'", str(ctx.exception))


class RewriteEnvTextTests(unittest.TestCase):
    def test_adds_compose_project_name_when_missing(self) -> None:
        original = "PROJECT=demo\n"
        rewritten = move.rewrite_env_text(original, "newproj")
        self.assertEqual(rewritten, "PROJECT=demo\nCOMPOSE_PROJECT_NAME=newproj\n")

    def test_replaces_existing_compose_project_name(self) -> None:
        original = "FOO=1\nCOMPOSE_PROJECT_NAME=oldproj\nBAR=2\n"
        rewritten = move.rewrite_env_text(original, "newproj")
        self.assertEqual(rewritten, "FOO=1\nCOMPOSE_PROJECT_NAME=newproj\nBAR=2\n")

    def test_preserves_other_text_and_adds_missing_newline(self) -> None:
        original = "FOO=1"
        rewritten = move.rewrite_env_text(original, "newproj")
        self.assertEqual(rewritten, "FOO=1\nCOMPOSE_PROJECT_NAME=newproj\n")

    def test_preserves_crlf_when_replacing_existing_value(self) -> None:
        original = "FOO=1\r\nCOMPOSE_PROJECT_NAME=oldproj\r\n"
        rewritten = move.rewrite_env_text(original, "newproj")
        self.assertEqual(rewritten, "FOO=1\r\nCOMPOSE_PROJECT_NAME=newproj\r\n")


class RollbackLedgerTests(unittest.TestCase):
    def test_rolls_back_in_reverse_order(self) -> None:
        ledger = move.RollbackLedger()
        calls: list[str] = []

        ledger.append("first", lambda: calls.append("first"))
        ledger.append("second", lambda: calls.append("second"))
        ledger.append("third", lambda: calls.append("third"))

        failures = ledger.rollback()

        self.assertEqual(failures, [])
        self.assertEqual(calls, ["third", "second", "first"])

    def test_collects_undo_failures_and_keeps_going(self) -> None:
        ledger = move.RollbackLedger()
        calls: list[str] = []

        def first() -> None:
            calls.append("first")

        def second() -> None:
            calls.append("second")
            raise RuntimeError("boom")

        def third() -> None:
            calls.append("third")

        ledger.append("first undo", first)
        ledger.append("second undo", second)
        ledger.append("third undo", third)

        failures = ledger.rollback()

        self.assertEqual(calls, ["third", "second", "first"])
        self.assertEqual(len(failures), 1)
        self.assertIn("second undo", failures[0])
        self.assertIn("boom", failures[0])


class PrefixExtractionTests(unittest.TestCase):
    def test_volume_suffix_for_project_volume(self) -> None:
        self.assertEqual(move.volume_suffix("demo_root", "demo"), "root")

    def test_volume_suffix_rejects_other_project(self) -> None:
        self.assertIsNone(move.volume_suffix("other_root", "demo"))

    def test_image_suffix_for_project_image(self) -> None:
        self.assertEqual(move.image_suffix("demo-python:latest", "demo"), "python")

    def test_image_suffix_handles_base_image(self) -> None:
        self.assertEqual(move.image_suffix("demo-base:latest", "demo"), "base")

    def test_image_suffix_rejects_other_project(self) -> None:
        self.assertIsNone(move.image_suffix("other-python:latest", "demo"))

    def test_rename_image_reference_preserves_tag(self) -> None:
        self.assertEqual(
            move.rename_image_reference("demo-python:latest", "demo", "renamed"),
            "renamed-python:latest",
        )


if __name__ == "__main__":
    unittest.main()
