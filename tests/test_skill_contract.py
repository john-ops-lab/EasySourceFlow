import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_feishu_cloud_documents_are_routed_through_easysourceflow(self):
        skill = (ROOT / "skills" / "easysourceflow" / "SKILL.md").read_text(encoding="utf-8")
        evals = json.loads(
            (ROOT / "skills" / "easysourceflow" / "evals" / "evals.json").read_text(encoding="utf-8")
        )

        feishu_reference = (ROOT / "skills" / "easysourceflow" / "references" / "feishu.md").read_text(encoding="utf-8")

        self.assertIn('version: "0.2.0"', skill)
        self.assertIn("authenticated cloud-document link", skill)
        self.assertIn("easysourceflow_submit_document", skill)
        self.assertIn("source_url", skill)
        self.assertIn("references/feishu.md", skill)
        self.assertIn("Never summarize or deliver the connector output directly", feishu_reference)
        self.assertIn("message.card", feishu_reference)

        feishu_evals = [item for item in evals["evals"] if ".feishu.cn/wiki/" in item.get("prompt", "")]
        self.assertEqual(len(feishu_evals), 1)
        expectations = " ".join(feishu_evals[0]["expectations"])
        self.assertIn("easysourceflow_submit_document", expectations)
        self.assertIn("Does not summarize", expectations)


if __name__ == "__main__":
    unittest.main()
