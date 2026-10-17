"""Track last portfolio / scheduled pipeline outcome for Grafana textfile metrics."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path


STATE_FILENAME = "last_pipeline_state.json"


def state_path(log_dir: Path | str) -> Path:
    return Path(log_dir) / STATE_FILENAME


def write_pipeline_state(
    log_dir: Path | str,
    *,
    epoch_seconds: int,
    success: bool,
    run_mode: str,
    token_exit: int | None = None,
    portfolio_exit: int | None = None,
    aggregate_exit: int | None = None,
) -> None:
    """Write atomic JSON consumed by scripts/export_kites_sync_metrics.py (chmod 0600)."""
    d = Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "epoch_seconds": int(epoch_seconds),
        "success": bool(success),
        "run_mode": run_mode,
        "token_exit": token_exit if token_exit is None else int(token_exit),
        "portfolio_exit": portfolio_exit if portfolio_exit is None else int(portfolio_exit),
        "aggregate_exit": aggregate_exit if aggregate_exit is None else int(aggregate_exit),
    }
    target = state_path(log_dir)
    tmp = target.with_suffix(".json.tmp")
    data = json.dumps(payload, separators=(",", ":"), sort_keys=False)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, target)
    try:
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    
    # Best-effort automatic export to Prometheus node_exporter textfile
    try_export_prometheus_metrics(payload)


def try_export_prometheus_metrics(payload: dict) -> None:
    """Best-effort export of Prometheus node-exporter textfile metric."""
    prom_str = os.environ.get("KITES_PROM_TEXTFILE", "/var/lib/node-exporter/textfile-collector/kites_automate.prom")
    prom_path = Path(prom_str)
    if not prom_path.parent.is_dir():
        return
    try:
        import tempfile
        success = 1 if payload.get("success") else 0
        ts = float(payload.get("epoch_seconds", 0))
        agg = int(payload.get("aggregate_exit", 0 if success else 1))
        content = (
            "# HELP kites_automate_last_success 1 if last_pipeline_state.json (or scheduled logs) marks a full successful run.\n"
            "# TYPE kites_automate_last_success gauge\n"
            f"kites_automate_last_success {success}\n"
            "# HELP kites_automate_last_run_timestamp_seconds Unix time (seconds) of the last scheduled run end (machine summary line preferred).\n"
            "# TYPE kites_automate_last_run_timestamp_seconds gauge\n"
            f"kites_automate_last_run_timestamp_seconds {ts:g}\n"
            "# HELP kites_automate_last_exit_code_aggregate 0 on full success else non-zero aggregate exit.\n"
            "# TYPE kites_automate_last_exit_code_aggregate gauge\n"
            f"kites_automate_last_exit_code_aggregate {agg}\n"
        )
        fd, tmp = tempfile.mkstemp(prefix=".kites_prom_", suffix=".tmp", dir=str(prom_path.parent))
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(content)
        os.replace(tmp, prom_path)
        try:
            os.chmod(prom_path, 0o660)
        except OSError:
            pass
    except Exception:
        pass


def load_pipeline_state(log_dir: Path | str) -> dict | None:
    p = state_path(log_dir)
    try:
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Write last_pipeline_state.json for Prometheus metrics exporter.")
    ap.add_argument("--log-dir", type=Path, required=True)
    ap.add_argument("--epoch", type=int, required=True)
    ap.add_argument("--mode", choices=("scheduled", "portfolio_only"), required=True)
    ap.add_argument("--success", type=int, choices=(0, 1), required=True)
    ap.add_argument("--token-exit", type=int, default=None)
    ap.add_argument("--portfolio-exit", type=int, default=None)
    ap.add_argument("--aggregate-exit", type=int, default=None)
    args = ap.parse_args()
    write_pipeline_state(
        args.log_dir,
        epoch_seconds=args.epoch,
        success=bool(args.success),
        run_mode=args.mode,
        token_exit=args.token_exit,
        portfolio_exit=args.portfolio_exit,
        aggregate_exit=args.aggregate_exit,
    )
    print(f"wrote {state_path(args.log_dir)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
