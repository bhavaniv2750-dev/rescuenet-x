"""Check the configuration this server would start with, WITHOUT starting it (and without printing any secret).

    python scripts/check_config.py          # exit code 1 if the server would refuse to start in this mode

Findings are FATAL (production refuses to start), WARNING (starts, but fix it) or INFO. Email is reported as unavailable unless a
provider is configured, and a configured SMTP server is never claimed to have been tested.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import startup_checks  # noqa: E402


def main() -> int:
    findings = startup_checks.evaluate()
    for f in findings:
        print(f"{f.level:<8} {f.code}: {f.message}")
    return 1 if any(f.level == startup_checks.FATAL for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
