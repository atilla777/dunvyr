import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


DEV_SCRIPT = Path(__file__).resolve().parents[1] / "dev.sh"


class DevOriginsTest(unittest.TestCase):
    def run_dev(self, ip_script, host="0.0.0.0"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            shutil.copy(DEV_SCRIPT, root / "scripts/dev.sh")
            (root / "backend/.venv/bin").mkdir(parents=True)
            (root / "backend/.venv/bin/python").touch(mode=0o755)
            (root / "frontend/node_modules").mkdir(parents=True)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            commands = {
                "ip": ip_script,
                "hostname": "printf '192.168.50.9 10.0.0.2\\n'",
                "setsid": 'exec /usr/bin/setsid "$@"',
                "mise": 'if [[ " $* " == *" uv run "* ]]; then printf "%s" "$DUNVYR_ALLOWED_ORIGINS" > "$CAPTURE"; else sleep 2; fi',
            }
            for name, body in commands.items():
                path = bin_dir / name
                path.write_text(f"#!/usr/bin/env bash\n{body}\n")
                path.chmod(0o755)
            capture = root / "origins"
            env = os.environ | {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "CAPTURE": str(capture),
                "DUNVYR_DEV_HOST": host,
                "DUNVYR_FRONTEND_PORT": "5317",
                "DUNVYR_BACKEND_PORT": "8000",
            }
            result = subprocess.run(
                ["bash", str(root / "scripts/dev.sh")],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertIn("DUNVYR_ALLOWED_ORIGINS", result.stdout)
            line = next(
                line
                for line in result.stdout.splitlines()
                if "DUNVYR_ALLOWED_ORIGINS" in line
            )
            origins = line.rsplit(": ", 1)[1].split(",")
            self.assertEqual(capture.read_text(), ",".join(origins))
            self.assertEqual(len(origins), len(set(origins)))
            return set(origins), result.stdout

    def test_vpn_default_and_wifi_secondary(self):
        ip_script = r"""if [[ "$*" == "-4 route get 1.1.1.1" ]]; then
  echo '1.1.1.1 dev tun0 src 10.8.0.2 uid 1000'
elif [[ "$*" == "-o -4 addr show up scope global" ]]; then
  echo '2: tun0    inet 10.8.0.2/24 scope global tun0'
  echo '3: wlan0    inet 192.168.50.9/24 brd 192.168.50.255 scope global dynamic wlan0'
fi"""
        origins, output = self.run_dev(ip_script)
        self.assertEqual(
            origins,
            {
                "http://127.0.0.1:5317",
                "http://localhost:5317",
                "http://10.8.0.2:5317",
                "http://192.168.50.9:5317",
            },
        )
        self.assertEqual(output.count("  LAN:      http://192.168.50.9:5317\n"), 1)
        self.assertEqual(output.count("  LAN:      http://10.8.0.2:5317\n"), 1)
        self.assertIn("            http://192.168.50.9:8000/health\n", output)

        explicit_origins, _ = self.run_dev(ip_script, host="192.168.50.9")
        self.assertEqual(explicit_origins, origins)

    def test_fallback_and_explicit_host(self):
        origins, _ = self.run_dev("exit 1", host="devbox.local")
        self.assertEqual(
            origins,
            {
                "http://127.0.0.1:5317",
                "http://localhost:5317",
                "http://192.168.50.9:5317",
                "http://devbox.local:5317",
            },
        )


if __name__ == "__main__":
    unittest.main()
