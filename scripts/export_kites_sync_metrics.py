#!/usr/bin/env python3
"""Write Prometheus node_exporter textfile metrics for Grafana from kites automate logs."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

SUMMARY_LINE = re.compile(
    r"^KITES_RUN_SUMMARY\s+epoch_seconds=(?P<epoch>\d+)\s+"
    r"token_exit=(?P<tok>-?\d+)\s+portfolio_exit=(?P<port>-?\d+)\s*$"
)

STATE_FILENAME = "last_pipeline_state.json"


def _parse_summary_line(lines: list[str]) -> dict[str, int] | None:
    for line in reversed(lines):
        m = SUMMARY_LINE.match(line.strip())
        if m:
            return {
                "epoch_seconds": int(m.group("epoch")),
                "token_exit": int(m.group("tok")),
                "portfolio_exit": int(m.group("port")),
            }
    return None


def _load_pipeline_state(log_dir: Path) -> tuple[int, float, int, str] | None:
    p = log_dir / STATE_FILENAME
    if not p.is_file():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        ok = bool(payload.get("success"))
        epoch = float(payload["epoch_seconds"])
        agg_raw = payload.get("aggregate_exit")
        if agg_raw is None:
            agg = 0 if ok else 1
        else:
            agg = int(agg_raw)
        succ = 1 if ok else 0
        return succ, epoch, agg, "last_pipeline_state.json"
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _best_summary_run_log(log_dir: Path) -> tuple[int, float, int, str] | None:
    best_epoch = -1
    best_summ: dict[str, int] | None = None
    best_name = ""
    for path in log_dir.glob("run_*.log"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in text:
            m = SUMMARY_LINE.match(line.strip())
            if m:
                epoch = int(m.group("epoch"))
                if epoch > best_epoch:
                    best_epoch = epoch
                    best_summ = {
                        "epoch_seconds": epoch,
                        "token_exit": int(m.group("tok")),
                        "portfolio_exit": int(m.group("port")),
                    }
                    best_name = path.name
    if best_summ:
        tok_ok = best_summ["token_exit"] == 0
        port_ok = best_summ["portfolio_exit"] == 0
        agg = 0 if (tok_ok and port_ok) else 1
        succ = 1 if agg == 0 else 0
        return succ, float(best_summ["epoch_seconds"]), agg, f"summary_max_epoch:{best_name}"
    return None


def derive_state(log_dir: Path) -> tuple[int, float, int, str]:
    """
    Returns success (0 or 1), last_run_unix, exit_code_aggregate, notes.
    Prefer last_pipeline_state.json (run-once / scheduled writers), then newest KITES_RUN_SUMMARY
    among run_*.log, then heuristic on newest log file only.
    """
    st = _load_pipeline_state(log_dir)
    if st:
        return st
    summed = _best_summary_run_log(log_dir)
    if summed:
        return summed
    runs = sorted(log_dir.glob("run_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in runs:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        summ = _parse_summary_line(text)
        if summ:
            tok_ok = summ["token_exit"] == 0
            port = summ["portfolio_exit"]
            port_ok = port == 0
            agg = 0 if (tok_ok and port_ok) else 1
            success = 1 if agg == 0 else 0
            return success, float(summ["epoch_seconds"]), agg, f"summary:{path.name}"
        tail = "\n".join(text[-240:])
        mtime_ts = float(path.stat().st_mtime)
        if "❌ Token renewal failed" in tail:
            return 0, mtime_ts, 1, f"fallback_token_fail:{path.name}"
        if "✅ Token renewal completed" in tail:
            if "✅ Portfolio update completed" in tail:
                return 1, mtime_ts, 0, f"fallback_ok:{path.name}"
            if "⚠️ Portfolio update finished with errors" in tail:
                return 0, mtime_ts, 1, f"fallback_portfolio_partial:{path.name}"

    return 0, 0.0, 1, "no_run_logs"


def emit_prom(success: int, last_ts: float, aggregate_exit: int) -> str:
    lines = [
        "# HELP kites_automate_last_success 1 if last_pipeline_state.json (or scheduled logs) marks a full successful run.",
        "# TYPE kites_automate_last_success gauge",
        f"kites_automate_last_success {success}",
        "# HELP kites_automate_last_run_timestamp_seconds Unix time (seconds) of the last scheduled run end (machine summary line preferred).",
        "# TYPE kites_automate_last_run_timestamp_seconds gauge",
        f"kites_automate_last_run_timestamp_seconds {last_ts:g}",
        "# HELP kites_automate_last_exit_code_aggregate 0 on full success else non-zero aggregate exit.",
        "# TYPE kites_automate_last_exit_code_aggregate gauge",
        f"kites_automate_last_exit_code_aggregate {aggregate_exit}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log-dir", type=Path, default=None, help="Directory containing run_*.log files")
    ap.add_argument(
        "--textfile",
        type=Path,
        default=Path(os.environ.get("KITES_PROM_TEXTFILE", "/var/lib/node-exporter/textfile-collector/kites_automate.prom")),
    )
    args = ap.parse_args()
    log_dir = args.log_dir or Path(os.environ.get("KITES_LOG_DIR", Path.home() / "kites-automate/logs"))
    if not log_dir.is_dir():
        print(f"log dir missing: {log_dir}", flush=True)
        # Still expose zeros so Grafana shows “never ran” distinctly from success
        content = emit_prom(0, 0.0, 1)
    else:
        success, ts, agg, note = derive_state(log_dir)
        content = emit_prom(success, ts, agg)
        print(f"kites_automate metrics: {note} success={success} ts={ts}", flush=True)

    args.textfile.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".kites_prom_", suffix=".tmp", dir=str(args.textfile.parent))
    try:
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(content)
        os.replace(tmp, args.textfile)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass

    try:
        # Prefer group readability for prometheus (textfile collector dir is group-sticky prometheus).
        os.chmod(args.textfile, 0o660)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
