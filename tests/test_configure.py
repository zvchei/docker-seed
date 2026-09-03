import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import configure
import harvest


class ConfigureParseEnvTests(unittest.TestCase):
    def test_parse_preserves_order_and_skips_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "# comment\n"
                "A=1\n"
                "\n"
                "B=2\n"
                "A=ignored\n"
            )
            with patch("builtins.print"):
                raw_lines, vars_ = configure._parse_env(env_file)
            self.assertEqual(len(raw_lines), 5)
            self.assertEqual(list(vars_.items()), [("A", "1"), ("B", "2")])


class ConfigureSeedTests(unittest.TestCase):
    def test_seed_copies_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / ".env.template"
            dest = Path(tmp) / ".env"
            template.write_text("PROJECT=from-template\n")
            with patch("builtins.print"):
                configure.seed_env_from_template(dest, template)
            self.assertEqual(dest.read_text(), "PROJECT=from-template\n")


class ConfigureEnvTests(unittest.TestCase):
    def test_configure_updates_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "# keep me\n"
                "PROJECT=old\n"
                "CONTAINER_USER=user\n"
            )
            answers = iter(["new-project", "", "y"])
            with (
                patch("builtins.input", side_effect=lambda _prompt="": next(answers)),
                patch("builtins.print"),
            ):
                configure.configure_env(env_file)
            text = env_file.read_text()
            self.assertIn("# keep me\n", text)
            self.assertIn("PROJECT=new-project\n", text)
            self.assertIn("CONTAINER_USER=user\n", text)

    def test_configure_missing_env_exits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / ".env"
            with (
                patch("builtins.print"),
                self.assertRaises(SystemExit) as ctx,
            ):
                configure.configure_env(missing)
            self.assertEqual(ctx.exception.code, 1)


class HarvestEnsureEnvTests(unittest.TestCase):
    def test_skips_configure_when_env_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            env_file = work / ".env"
            env_file.write_text("PROJECT=existing\n")
            with (
                patch.object(harvest, "ENV_FILE", env_file),
                patch.object(configure, "seed_env_from_template") as seed,
                patch.object(configure, "configure_env") as cfg,
                patch("builtins.print"),
            ):
                harvest.ensure_env()
            seed.assert_not_called()
            cfg.assert_not_called()

    def test_seeds_and_configures_when_env_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            env_file = work / ".env"
            template = work / ".env.template"
            template.write_text("PROJECT=template\n")
            with (
                patch.object(harvest, "ENV_FILE", env_file),
                patch.object(configure, "ENV_TEMPLATE", template),
                patch.object(configure, "configure_env") as cfg,
                patch("builtins.print"),
            ):
                harvest.ensure_env()
            self.assertTrue(env_file.is_file())
            self.assertEqual(env_file.read_text(), "PROJECT=template\n")
            cfg.assert_called_once_with(env_file)
