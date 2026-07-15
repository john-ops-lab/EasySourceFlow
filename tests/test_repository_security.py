import unittest
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_LABEL = "app.easysourceflow.daemon"
MAINTENANCE_LABEL = "app.easysourceflow.maintenance"


class RepositorySecurityTests(unittest.TestCase):
    def test_launchagent_defaults_are_project_owned(self):
        script = (ROOT / "scripts" / "easysourceflow").read_text(encoding="utf-8")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")

        for label in (SERVICE_LABEL, MAINTENANCE_LABEL):
            self.assertIn(label, script)
            self.assertIn(label, example)

    def test_gitignore_covers_local_sensitive_artifacts(self):
        rules = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())
        required = {
            ".env",
            ".env.*",
            "!.env.example",
            "var/",
            "backup/",
            "output/",
            "*.sqlite3",
            "*.db",
            "*.log",
            "*.cookies",
            "*cookies*.txt",
            "secrets/",
        }

        self.assertTrue(required.issubset(rules))

    def test_security_scan_uses_generic_workspace_pattern(self):
        policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("workspace-[A-Za-z0-9_-]+", policy)

    def test_tracked_files_do_not_contain_personal_machine_identifiers(self):
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout.split(b"\0")
        forbidden = re.compile(
            "|".join(
                [
                    r"/" + "Users" + r"/[A-Za-z0-9._-]+/",
                    r"/home/[A-Za-z0-9._-]+/",
                    r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\",
                    "workspace-" + "varys",
                    "john-" + "ops-lab",
                    r"com\." + "king",
                ]
            ),
            re.IGNORECASE,
        )
        findings = []
        for raw_path in tracked:
            if not raw_path:
                continue
            path = ROOT / raw_path.decode("utf-8")
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if forbidden.search(content):
                findings.append(str(path.relative_to(ROOT)))
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
