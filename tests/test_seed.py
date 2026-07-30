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


class SeedContainerVolumeOverrideTests(unittest.TestCase):
    def _make_container(self, volumes: dict) -> dict:
        return {
            "name": "svc",
            "enabled": True,
            "templates": [],
            "volumes": volumes,
        }

    def test_container_volumes_are_merged_into_output(self) -> None:
        container = self._make_container({"hf_cache": ".cache/huggingface"})
        merged = seed.build_merged_for_container(container, [container])
        self.assertIn("hf_cache", merged["volumes"])
        self.assertEqual(merged["volumes"]["hf_cache"], ".cache/huggingface")

    def test_container_volumes_override_template_volumes(self) -> None:
        """A volume key in containers.json overwrites the same key from templates."""
        container = {
            "name": "svc",
            "enabled": True,
            "templates": ["python"],
            "volumes": {"cache": ".cache/custom"},
        }
        merged = seed.build_merged_for_container(container, [container])
        self.assertEqual(merged["volumes"]["cache"], ".cache/custom")

    def test_container_volumes_appear_in_compose(self) -> None:
        container = self._make_container({"hf_cache": ".cache/huggingface"})
        merged = seed.build_merged_for_container(container, [container])
        compose = seed.generate_compose("svc", merged)
        self.assertIn("- hf_cache:/home/${CONTAINER_USER}/.cache/huggingface", compose)
        self.assertIn("    hf_cache:", compose)


class SeedContainerAptPackagesOverrideTests(unittest.TestCase):
    def test_container_apt_packages_are_added(self) -> None:
        container = {
            "name": "svc",
            "enabled": True,
            "templates": [],
            "apt_packages": ["curl", "jq"],
        }
        merged = seed.build_merged_for_container(container, [container])
        self.assertIn("curl", merged["apt_packages"])
        self.assertIn("jq", merged["apt_packages"])

    def test_container_apt_packages_union_with_template(self) -> None:
        container = {
            "name": "svc",
            "enabled": True,
            "templates": ["python"],
            "apt_packages": ["jq"],
        }
        merged = seed.build_merged_for_container(container, [container])
        # python template provides python3-venv and python3-dev; jq is appended
        self.assertIn("python3-venv", merged["apt_packages"])
        self.assertIn("jq", merged["apt_packages"])

    def test_container_apt_packages_deduplicated(self) -> None:
        container = {
            "name": "svc",
            "enabled": True,
            "templates": ["python"],
            "apt_packages": ["python3-venv"],  # already in python template
        }
        merged = seed.build_merged_for_container(container, [container])
        self.assertEqual(merged["apt_packages"].count("python3-venv"), 1)


class SeedNetworkGenerationTests(unittest.TestCase):
    def test_internal_network_emits_internal_true(self) -> None:
        merged = {"networks": [{"name": "llama_local", "internal": True}]}
        compose = seed.generate_compose("llama_cpp", merged)
        self.assertIn("networks:", compose)
        self.assertIn("    llama_local:", compose)
        self.assertIn("      internal: true", compose)

    def test_external_network_emits_external_true(self) -> None:
        merged = {"networks": [{"name": "some_net", "external": True}]}
        compose = seed.generate_compose("svc", merged)
        self.assertIn("    some_net:", compose)
        self.assertIn("      external: true", compose)
        self.assertNotIn("internal: true", compose)

    def test_internal_and_external_both_emitted(self) -> None:
        """internal and external are orthogonal properties; both can be set."""
        merged = {"networks": [{"name": "pre_existing_isolated", "external": True, "internal": True}]}
        compose = seed.generate_compose("svc", merged)
        self.assertIn("      external: true", compose)
        self.assertIn("      internal: true", compose)

    def test_plain_network_emits_no_flags(self) -> None:
        merged = {"networks": [{"name": "default_net"}]}
        compose = seed.generate_compose("svc", merged)
        self.assertIn("    default_net:", compose)
        self.assertNotIn("external: true", compose)
        self.assertNotIn("internal: true", compose)


if __name__ == "__main__":
    unittest.main()
