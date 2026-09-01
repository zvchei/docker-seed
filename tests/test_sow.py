import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cleanup
import harvest
import sow


class SeedVolumeResolutionTests(unittest.TestCase):
    def test_container_specific_volume_is_prefixed_in_compose(self) -> None:
        merged = {
            "volumes": {
                "local": {"path": ".local", "container_specific": True},
                "cache": ".cache/pip",
            }
        }

        compose = sow.generate_compose("python_dev", merged)

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

        dockerfile = sow.generate_dockerfile(merged)

        self.assertIn("RUN mkdir -p $HOME/.local/share", dockerfile)

    def test_invalid_container_specific_type_raises(self) -> None:
        with self.assertRaises(SystemExit):
            sow.generate_compose(
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
        merged = sow.build_merged_for_container(container, [container])
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
        merged = sow.build_merged_for_container(container, [container])
        self.assertEqual(merged["volumes"]["cache"], ".cache/custom")

    def test_container_volumes_appear_in_compose(self) -> None:
        container = self._make_container({"hf_cache": ".cache/huggingface"})
        merged = sow.build_merged_for_container(container, [container])
        compose = sow.generate_compose("svc", merged)
        self.assertIn("- hf_cache:/home/${CONTAINER_USER}/.cache/huggingface", compose)
        self.assertIn("    hf_cache:", compose)


class SeedServiceTemplateTests(unittest.TestCase):
    def test_service_reference_merges_before_following_template_and_child(self) -> None:
        containers = [
            {
                "name": "@shared",
                "templates": [],
                "apt_packages": ["jq"],
                "env_vars": {"ORDER": "parent", "SHARED": "yes"},
            },
            {
                "name": "consumer",
                "templates": ["service:@shared", "template:python"],
                "env_vars": {"ORDER": "child"},
            },
        ]

        merged = sow.build_merged_for_container(containers[1], containers)

        self.assertEqual(merged["apt_packages"], ["jq", "python3-venv", "python3-dev"])
        self.assertEqual(merged["env_vars"]["SHARED"], "yes")
        self.assertEqual(merged["env_vars"]["ORDER"], "child")

    def test_service_references_are_applied_in_order(self) -> None:
        containers = [
            {"name": "@first", "templates": [], "env_vars": {"ORDER": "first"}},
            {"name": "@second", "templates": [], "env_vars": {"ORDER": "second"}},
            {
                "name": "consumer",
                "templates": ["@first", "@second"],
            },
        ]

        merged = sow.build_merged_for_container(containers[2], containers)

        self.assertEqual(merged["env_vars"]["ORDER"], "second")

    def test_own_service_name_prefers_same_named_template(self) -> None:
        container = {"name": "python", "templates": ["python"]}

        merged = sow.build_merged_for_container(container, [container])

        self.assertIn("python3-venv", merged["apt_packages"])

    def test_ambiguous_unqualified_reference_requires_qualifier(self) -> None:
        containers = [
            {"name": "python", "templates": []},
            {"name": "consumer", "templates": ["python"]},
        ]

        with self.assertRaises(SystemExit):
            sow.build_merged_for_container(containers[1], containers)

    def test_qualified_references_select_service_or_template(self) -> None:
        containers = [
            {
                "name": "python",
                "templates": [],
                "env_vars": {"SOURCE": "service"},
            },
            {
                "name": "service_consumer",
                "templates": ["service:python"],
            },
            {
                "name": "template_consumer",
                "templates": ["template:python"],
            },
        ]

        service_merged = sow.build_merged_for_container(containers[1], containers)
        template_merged = sow.build_merged_for_container(containers[2], containers)

        self.assertEqual(service_merged["env_vars"]["SOURCE"], "service")
        self.assertIn("python3-venv", template_merged["apt_packages"])

    def test_service_reference_does_not_reuse_image(self) -> None:
        containers = [
            {"name": "base", "templates": []},
            {"name": "derived", "extends": "base"},
            {"name": "consumer", "templates": ["service:derived"]},
        ]

        merged = sow.build_merged_for_container(containers[2], containers)

        self.assertNotIn("extended_service", merged)

    def test_circular_service_reference_raises(self) -> None:
        containers = [
            {"name": "@a", "templates": ["service:@b"]},
            {"name": "@b", "templates": ["service:@a"]},
        ]

        with self.assertRaises(SystemExit):
            sow.build_merged_for_container(containers[0], containers)

    def test_extends_cannot_target_abstract_service(self) -> None:
        containers = [
            {"name": "@base", "templates": []},
            {"name": "consumer", "extends": "@base"},
        ]

        with self.assertRaises(SystemExit):
            sow.validate_extends(containers)

    def test_abstract_service_cannot_extend(self) -> None:
        containers = [
            {"name": "base", "templates": []},
            {"name": "@consumer", "extends": "base"},
        ]

        with self.assertRaises(SystemExit):
            sow.validate_extends(containers)

    def test_abstract_service_is_not_generated(self) -> None:
        containers = [
            {"name": "@shared", "templates": []},
            {"name": "consumer", "templates": ["@shared"]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            containers_file = work_dir / "containers.json"
            containers_file.write_text(json.dumps(containers))
            services_dir = work_dir / "services"

            with (
                patch.object(sow, "CONTAINERS_FILE", containers_file),
                patch.object(sow, "SERVICES_DIR", services_dir),
                patch.object(sow, "ASSETS_FILE", work_dir / "assets.json"),
                patch.object(sow, "sync_common"),
                patch.object(sow, "sync_env"),
            ):
                sow.main()

            self.assertFalse((services_dir / "@shared").exists())
            self.assertTrue((services_dir / "consumer" / "Dockerfile").is_file())

    def test_harvest_omits_abstract_services(self) -> None:
        containers = [
            {"name": "@shared"},
            {"name": "enabled"},
            {"name": "disabled", "enabled": False},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            containers_file = Path(tmp) / "containers.json"
            containers_file.write_text(json.dumps(containers))

            self.assertEqual(
                harvest.get_enabled_services(containers_file),
                ["enabled"],
            )

    def test_cleanup_omits_abstract_services_and_images(self) -> None:
        containers = [{"name": "@shared"}, {"name": "concrete"}]

        self.assertEqual(cleanup.declared_service_names(containers), {"concrete"})
        self.assertEqual(
            cleanup.image_service_names(containers),
            {"base", "concrete"},
        )


class SeedContainerAptPackagesOverrideTests(unittest.TestCase):
    def test_container_apt_packages_are_added(self) -> None:
        container = {
            "name": "svc",
            "enabled": True,
            "templates": [],
            "apt_packages": ["curl", "jq"],
        }
        merged = sow.build_merged_for_container(container, [container])
        self.assertIn("curl", merged["apt_packages"])
        self.assertIn("jq", merged["apt_packages"])

    def test_container_apt_packages_union_with_template(self) -> None:
        container = {
            "name": "svc",
            "enabled": True,
            "templates": ["python"],
            "apt_packages": ["jq"],
        }
        merged = sow.build_merged_for_container(container, [container])
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
        merged = sow.build_merged_for_container(container, [container])
        self.assertEqual(merged["apt_packages"].count("python3-venv"), 1)


class SeedNetworkGenerationTests(unittest.TestCase):
    def test_internal_network_emits_internal_true(self) -> None:
        merged = {"networks": [{"name": "llama_local", "internal": True}]}
        compose = sow.generate_compose("llama_cpp", merged)
        self.assertIn("networks:", compose)
        self.assertIn("    llama_local:", compose)
        self.assertIn("      internal: true", compose)

    def test_external_network_emits_external_true(self) -> None:
        merged = {"networks": [{"name": "some_net", "external": True}]}
        compose = sow.generate_compose("svc", merged)
        self.assertIn("    some_net:", compose)
        self.assertIn("      external: true", compose)
        self.assertNotIn("internal: true", compose)

    def test_internal_and_external_both_emitted(self) -> None:
        """internal and external are orthogonal properties; both can be set."""
        merged = {"networks": [{"name": "pre_existing_isolated", "external": True, "internal": True}]}
        compose = sow.generate_compose("svc", merged)
        self.assertIn("      external: true", compose)
        self.assertIn("      internal: true", compose)

    def test_plain_network_emits_no_flags(self) -> None:
        merged = {"networks": [{"name": "default_net"}]}
        compose = sow.generate_compose("svc", merged)
        self.assertIn("    default_net:", compose)
        self.assertNotIn("external: true", compose)
        self.assertNotIn("internal: true", compose)


if __name__ == "__main__":
    unittest.main()
