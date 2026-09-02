import tempfile
import unittest
from pathlib import Path

import transfer


class ParseVolumeSpecTests(unittest.TestCase):
    def test_service_volume_defaults_path_to_dot(self) -> None:
        self.assertEqual(
            transfer.parse_volume_spec("python:root"),
            ("python", "root", "."),
        )

    def test_relative_path(self) -> None:
        self.assertEqual(
            transfer.parse_volume_spec("python:root:src"),
            ("python", "root", "src"),
        )

    def test_path_may_contain_colons(self) -> None:
        self.assertEqual(
            transfer.parse_volume_spec("python:root:foo:bar"),
            ("python", "root", "foo:bar"),
        )

    def test_empty_path_becomes_dot(self) -> None:
        self.assertEqual(
            transfer.parse_volume_spec("python:root:"),
            ("python", "root", "."),
        )

    def test_missing_volume_raises(self) -> None:
        with self.assertRaises(ValueError):
            transfer.parse_volume_spec("python:")

    def test_no_colon_raises(self) -> None:
        with self.assertRaises(ValueError):
            transfer.parse_volume_spec("python")


class ClassifyAndDirectionTests(unittest.TestCase):
    def test_import_when_host_then_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            direction, host, spec = transfer.detect_direction(
                "../app",
                "python:root:src",
                {"python"},
                cwd,
            )
            self.assertEqual(direction, "import")
            self.assertEqual(host, "../app")
            self.assertEqual(spec, "python:root:src")

    def test_export_when_spec_then_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            direction, host, spec = transfer.detect_direction(
                "python:root:src",
                "../app",
                {"python"},
                cwd,
            )
            self.assertEqual(direction, "export")
            self.assertEqual(host, "../app")
            self.assertEqual(spec, "python:root:src")

    def test_host_path_with_colon_is_host_if_service_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            kind = transfer.classify_arg("weird:name", {"python"}, cwd)
            self.assertEqual(kind, "host")

    def test_both_specs_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            with self.assertRaises(ValueError) as ctx:
                transfer.detect_direction(
                    "python:root:a",
                    "python:cache:b",
                    {"python"},
                    cwd,
                )
            self.assertIn("both arguments", str(ctx.exception))

    def test_neither_spec_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            with self.assertRaises(ValueError) as ctx:
                transfer.detect_direction("./a", "./b", {"python"}, cwd)
            self.assertIn("neither argument", str(ctx.exception))

    def test_ambiguous_when_spec_shaped_local_directory_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            (cwd / "python:root:src").mkdir()
            with self.assertRaises(ValueError) as ctx:
                transfer.detect_direction(
                    "python:root:src",
                    "./out",
                    {"python"},
                    cwd,
                )
            self.assertIn("ambiguous", str(ctx.exception))


class ResolveVolumeKeyTests(unittest.TestCase):
    def test_exact_compose_key(self) -> None:
        mounts = {"root": "/home/user/proj", "cache": "/home/user/.cache/pip"}
        self.assertEqual(transfer.resolve_volume_key("cache", "python", mounts), "cache")

    def test_container_specific_short_name(self) -> None:
        mounts = {
            "root": "/home/user/proj",
            "chrome_local": "/home/user/.local",
        }
        self.assertEqual(
            transfer.resolve_volume_key("local", "chrome", mounts),
            "chrome_local",
        )

    def test_unknown_volume_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            transfer.resolve_volume_key("nope", "python", {"root": "/x"})
        self.assertIn("not mounted", str(ctx.exception))


class VolumeRelativePathTests(unittest.TestCase):
    mount = "/home/user/project"

    def test_dot_is_volume_root(self) -> None:
        self.assertEqual(transfer.volume_relative_path(".", self.mount), ".")

    def test_relative_path(self) -> None:
        self.assertEqual(transfer.volume_relative_path("src/app", self.mount), "src/app")

    def test_absolute_under_mount(self) -> None:
        self.assertEqual(
            transfer.volume_relative_path("/home/user/project/src", self.mount),
            "src",
        )

    def test_absolute_equal_to_mount(self) -> None:
        self.assertEqual(
            transfer.volume_relative_path("/home/user/project", self.mount),
            ".",
        )

    def test_absolute_outside_mount_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            transfer.volume_relative_path("/home/user/other", self.mount)
        self.assertIn("not under volume mount", str(ctx.exception))

    def test_parent_escape_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            transfer.volume_relative_path("foo/../../etc", self.mount)
        self.assertIn("escapes", str(ctx.exception))

    def test_normalized_relative_stays_inside(self) -> None:
        self.assertEqual(
            transfer.volume_relative_path("foo/../bar", self.mount),
            "bar",
        )


class ServiceVolumeMountsTests(unittest.TestCase):
    def test_parses_service_list_not_top_level_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docker-compose.yaml"
            path.write_text(
                "services:\n"
                "    python:\n"
                "        volumes:\n"
                "            - root:/home/${CONTAINER_USER}/${PROJECT}\n"
                "            - cache:/home/${CONTAINER_USER}/.cache/pip\n"
                "        build:\n"
                "            context: .\n"
                "\n"
                "volumes:\n"
                "    root:\n"
                "    cache:\n"
            )
            mounts = transfer.service_volume_mounts(path)
            self.assertEqual(
                mounts,
                {
                    "root": "/home/${CONTAINER_USER}/${PROJECT}",
                    "cache": "/home/${CONTAINER_USER}/.cache/pip",
                },
            )


class InterpolateMountTests(unittest.TestCase):
    def test_substitutes_env(self) -> None:
        self.assertEqual(
            transfer.interpolate_mount(
                "/home/${CONTAINER_USER}/${PROJECT}",
                {"CONTAINER_USER": "me", "PROJECT": "app"},
            ),
            "/home/me/app",
        )
