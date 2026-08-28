from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = ROOT / "scripts" / "setup_windows.ps1"


class WindowsSetupContractTests(unittest.TestCase):
    def test_setup_script_is_public_bootstrap_only(self) -> None:
        script = SETUP_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("https://www.opendesign.com/guestfiles/get", script)
        self.assertIn("Get-AuthenticodeSignature", script)
        self.assertIn("Get-FileHash", script)
        self.assertIn('"/a", $downloadedMsi', script)
        self.assertIn("TARGETDIR=$extractRoot", script)
        self.assertIn("MUNICIPAL_QTO_DWG_CONVERTER", script)
        self.assertIn("$OdaMsiPath", script)
        pinned_hashes = re.findall(r'\$odaMsiSha256 = "([0-9A-F]{64})"', script)
        self.assertEqual(len(pinned_hashes), 1)
        self.assertNotIn("data\\cad_inputs", script)
        self.assertNotIn("Invoke-RestMethod", script)


if __name__ == "__main__":
    unittest.main()
