import re
import unittest
from pathlib import Path


README = Path(__file__).resolve().parent.parent / "README.md"


class ReadmeCredentialSafetyTests(unittest.TestCase):
    def test_api_key_examples_do_not_put_secrets_in_shell_history(self) -> None:
        text = README.read_text(encoding="utf-8")

        unsafe_assignments = (
            r"export\s+OPENAI_API_KEY\s*=",
            r"\$env:OPENAI_API_KEY\s*=",
        )
        for pattern in unsafe_assignments:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, text))

        self.assertIn("IFS= read -rs OPENAI_API_KEY", text)
        self.assertIn(
            '$secureKey = Read-Host "OpenAI API Key" -AsSecureString',
            text,
        )
        self.assertNotIn(
            'Read-Host "OpenAI API Key" | codex login --with-api-key',
            text,
        )


if __name__ == "__main__":
    unittest.main()
