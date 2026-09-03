from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "standalone" / "sayelf-cq-municipal-cad-qto.html"
SKILL = ROOT / "standalone" / "skills" / "sayelf-cq-municipal-cad-qto" / "SKILL.md"
OPENAI_YAML = (
    ROOT
    / "standalone"
    / "skills"
    / "sayelf-cq-municipal-cad-qto"
    / "agents"
    / "openai.yaml"
)


class StandaloneDeliverableTests(unittest.TestCase):
    def test_html_is_single_file_local_api_shell(self) -> None:
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("data-generated-from=\"web/style.css\"", html)
        self.assertIn("data-generated-from=\"web/app.js\"", html)
        self.assertIn("http://127.0.0.1:8765", html)
        self.assertNotIn('<link rel="stylesheet" href="/style.css">', html)
        self.assertNotIn('<script src="/app.js"></script>', html)
        self.assertIn("/api/cad/files", html)
        self.assertIn("/api/cad/jobs/", html)

    def test_skill_is_scoped_to_cad_quantity_takeoff(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("name: sayelf-cq-municipal-cad-qto", skill)
        self.assertIn("municipal_qto_inspect_dxf_batch", skill)
        self.assertIn("municipal_qto_calculate", skill)
        self.assertIn("municipal_qto_export_job", skill)
        self.assertIn("sayelf-municipal-cost-loop", skill)
        self.assertIn("Observation", skill)
        self.assertIn("Fact", skill)

    def test_codex_metadata_exists(self) -> None:
        metadata = OPENAI_YAML.read_text(encoding="utf-8")
        self.assertIn("display_name:", metadata)
        self.assertIn("default_prompt:", metadata)


if __name__ == "__main__":
    unittest.main()
