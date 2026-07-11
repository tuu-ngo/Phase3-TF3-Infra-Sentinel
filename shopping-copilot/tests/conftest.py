"""
tests/conftest.py — Log kết quả từng bài test ra console + file.
"""

import logging
import sys
from datetime import datetime

# ── Logging format ──
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)

# ── File handler: ghi log riêng vào file ──
_file_handler = logging.FileHandler(
    f"tests/logs/test_tools_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    encoding="utf-8",
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger().addHandler(_file_handler)

logger = logging.getLogger("test_tools")


def pytest_runtest_logreport(report):
    """Ghi log cho từng bài test khi kết thúc."""
    if report.when != "call":
        return

    duration_ms = int((report.duration or 0) * 1000)

    status = {
        "passed": "✅ PASS",
        "failed": "❌ FAIL",
        "skipped": "⏭️ SKIP",
    }.get(report.outcome, f"? {report.outcome}")

    msg = f"{status} | {report.nodeid} ({duration_ms}ms)"
    if report.outcome == "failed":
        tb_lines = report.longreprtext.splitlines()
        brief = tb_lines[-1] if tb_lines else "unknown error"
        msg += f"\n         → {brief}"

    logger.info(msg)
