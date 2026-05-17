import unittest

import seed


class SeedVolumeResolutionTests(unittest.TestCase):
    def test_container_specific_volume_is_prefixed_in_compose(self) -> None:
        merged = {
            "volumes": {
                "local": {"path": ".local", "container_specific": True},
                "cache": ".cache/pip",
            }
        }

        compose = seed.generate_compose("python_dev", merged)

        self.assertIn("- python_dev_local:/home/${CONTAINER_USER}/.local", compose)
        self.assertIn("- cache:/home/${CONTAINER_USER}/.cache/pip", compose)
        self.assertIn("    python_dev_local:", compose)
        self.assertIn("    cache:", compose)

    def test_object_volume_path_is_used_for_dockerfile_directories(self) -> None:
        merged = {
            "volumes": {"state": {"path": ".local/share", "container_specific": True}},
            "root_fragments": [],
            "user_fragments": [],
        }

        dockerfile = seed.generate_dockerfile(merged)

        self.assertIn("RUN mkdir -p $HOME/.local/share", dockerfile)

    def test_invalid_container_specific_type_raises(self) -> None:
        with self.assertRaises(SystemExit):
            seed.generate_compose(
                "bad",
                {"volumes": {"local": {"path": ".local", "container_specific": "yes"}}},
            )


if __name__ == "__main__":
    unittest.main()
