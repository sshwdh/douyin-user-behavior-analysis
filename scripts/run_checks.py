"""运行编码规范检查和单元测试，并保存可追溯日志。"""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    """依次运行质量门禁，任何失败都导致非零退出。"""
    commands = [
        ["-m", "black", "--check", "src", "tests", "scripts"],
        ["-m", "isort", "--check-only", "src", "tests", "scripts"],
        ["-m", "flake8", "src", "tests", "scripts"],
        ["-m", "mypy", "src"],
        ["-m", "pylint", "src"],
        ["scripts/check_project_rules.py"],
        ["-m", "pytest", "-q"],
    ]
    log = [f"UTC: {datetime.now(timezone.utc).isoformat()}", sys.version]
    failures = 0
    for command in commands:
        result = subprocess.run(
            [sys.executable, *command], capture_output=True, text=True, check=False
        )
        log.extend(
            [
                f"COMMAND: python {' '.join(command)}",
                result.stdout,
                result.stderr,
                f"EXIT: {result.returncode}",
            ]
        )
        failures += int(result.returncode != 0)
    Path("reports/quality_checks.txt").write_text("\n".join(log), encoding="utf-8")
    if failures:
        raise SystemExit(f"{failures} 项检查失败，详见 reports/quality_checks.txt")
    print("All quality checks passed.")


if __name__ == "__main__":
    main()
