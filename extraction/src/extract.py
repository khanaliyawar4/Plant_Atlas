from __future__ import annotations

import argparse
import datetime as _dt
import logging
import signal
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import orjson
import yaml
from tqdm import tqdm

from .article_io import (
    SectionConfig, iter_article_paths, load_article, parse_filename,
)
from .llm_client import LLMClient
from .postprocess import (
    EXTRACTION_JSON_SCHEMA, GATE_JSON_SCHEMA,
    parse_extraction, parse_gate, public_row,
    render_rows_tsv, tsv_header,
)
from .prefilter import Prefilter
from .progress import JsonlLogger, ProgressFile, TsvAppender
from .prompts import build_extract_messages, build_gate_messages

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extract plant-bioengineering info from PMC plain-text articles.",
    )
    p.add_argument("--config", type=Path,
                   default=Path(__file__).resolve().parent.parent / "config" / "default.yaml")
    p.add_argument("--input-dir",  type=Path, default=None)
    p.add_argument("--output-tsv", type=Path, default=None)
    p.add_argument("--log-file",   type=Path, default=None)
    p.add_argument("--limit", type=int, default=None,
                   help="process at most N articles (for smoke tests)")
    p.add_argument("--concurrency", type=int, default=None,
                   help="articles processed in parallel (in-flight LLM requests). "
                        "Overrides extraction.concurrency. 1 = sequential.")
    p.add_argument("--verbose", "-v", action="count", default=0)
    return p.parse_args()

def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

_shutdown = False

def _install_signal_handlers() -> None:
    def handler(signum, _frame):
        global _shutdown
        logging.warning("received signal %d -- draining in-flight batch then stopping", signum)
        _shutdown = True
    signal.signal(signal.SIGINT,  handler)
    signal.signal(signal.SIGTERM, handler)

class EvidenceAudit:

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._f = open(path, "ab")

    def record(self, *, pmcid: str, decision: str, reason: str,
               row: dict, evidence_quote: str) -> None:
        rec = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"),
            "pmcid": pmcid,
            "decision": decision,
            "reason": reason,
            "evidence_quote": evidence_quote,
            "row": row,
        }
        self._f.write(orjson.dumps(rec))
        self._f.write(b"\n")

    def close(self) -> None:
        try:
            self._f.flush()
            self._f.close()
        except Exception:
            pass

def process_one(path: Path, *, section_cfg, prefilter, client, gen,
                gate_schema, extract_schema, verify_evidence_on) -> dict:
    ev: list = []
    audit: list = []
    st: dict = {}

    def inc(k, n=1):
        st[k] = st.get(k, 0) + n

    def result(*, pmcid, mark, rows_tsv=None, done=False):
        return {"pmcid": pmcid, "events": ev, "audit": audit,
                "rows_tsv": rows_tsv, "mark": mark, "stats": st, "done": done}

    article = load_article(path, section_cfg)
    if article is None:
        ev.append(("article.bad_filename", {"path": str(path)}))
        inc("errors")
        return result(pmcid=None, mark=False)

    pmcid = article.pmcid
    t_article = time.monotonic()

    pre = prefilter.check(article)
    if not pre.keep:
        ev.append(("prefilter.skip", {"pmcid": pmcid, "reason": pre.reason}))
        inc("prefilter_skip")
        return result(pmcid=pmcid, mark=True)

    try:
        gate_reply = client.chat(
            messages=build_gate_messages(
                pmcid=pmcid, doi=article.doi,
                article_type=article.article_type, body=article.body,
            ),
            max_tokens=int(gen["max_tokens_gate"]),
            temperature=float(gen["temperature"]),
            top_p=float(gen["top_p"]),
            enable_thinking=bool(gen["gate_enable_thinking"]),
            response_format_json=True,
            guided_json=gate_schema,
        )
    except Exception as exc:
        ev.append(("gate.error", {"pmcid": pmcid, "error": repr(exc)}))
        inc("errors")
        return result(pmcid=pmcid, mark=False)

    gate = parse_gate(gate_reply.content)
    if not gate.qualifies:
        ev.append(("gate.skip", {
            "pmcid": pmcid, "reason": gate.reason,
            "parse_error": gate.parse_error,
            "usage_prompt": gate_reply.usage_prompt,
            "usage_completion": gate_reply.usage_completion,
        }))
        inc("gate_skip")
        return result(pmcid=pmcid, mark=True)

    try:
        extract_reply = client.chat(
            messages=build_extract_messages(
                pmcid=pmcid, doi=article.doi, body=article.body,
            ),
            max_tokens=int(gen["max_tokens_extract"]),
            temperature=float(gen["temperature"]),
            top_p=float(gen["top_p"]),
            enable_thinking=bool(gen["extract_enable_thinking"]),
            response_format_json=True,
            guided_json=extract_schema,
        )
    except Exception as exc:
        ev.append(("extract.error", {"pmcid": pmcid, "error": repr(exc)}))
        inc("errors")
        return result(pmcid=pmcid, mark=False)

    body_for_check = article.body if verify_evidence_on else None
    parsed = parse_extraction(extract_reply.content, body=body_for_check)
    if parsed.parse_error:
        ev.append(("extract.parse_error", {
            "pmcid": pmcid,
            "parse_error": parsed.parse_error,
            "raw_head": extract_reply.content[:400],
        }))

    for row in parsed.rows:
        if row["pmcid"] == "NA":
            row["pmcid"] = pmcid
        if row["doi"] == "NA" and article.doi:
            row["doi"] = article.doi

    if not parsed.rows:
        ev.append(("extract.empty", {
            "pmcid": pmcid,
            "gate_reason": gate.reason,
            "usage_prompt": extract_reply.usage_prompt,
            "usage_completion": extract_reply.usage_completion,
        }))
        inc("extract_empty")
        return result(pmcid=pmcid, mark=True)

    accepted_rows: list = []
    n_reject = 0
    for row in parsed.rows:
        ev_ok    = row.get("_evidence_ok")
        ev_diag  = row.get("_evidence_diag", "")
        ev_quote = row.get("_evidence_quote", "")
        pub      = public_row(row)
        if ev_ok is False:
            n_reject += 1
            audit.append({
                "pmcid": pmcid, "decision": "rejected_evidence",
                "reason": ev_diag, "row": pub, "evidence_quote": ev_quote,
            })
            ev.append(("extract.evidence_reject", {
                "pmcid": pmcid, "diag": ev_diag, "quote_head": ev_quote[:160],
            }))
        else:
            accepted_rows.append(pub)
            audit.append({
                "pmcid": pmcid, "decision": "accepted",
                "reason": ev_diag if ev_diag else "verification disabled",
                "row": pub, "evidence_quote": ev_quote,
            })

    inc("rows_rejected_evidence", n_reject)

    if not accepted_rows:
        ev.append(("extract.all_rejected_evidence", {
            "pmcid": pmcid, "proposed": len(parsed.rows),
        }))
        return result(pmcid=pmcid, mark=True)

    inc("rows_written", len(accepted_rows))
    ev.append(("article.done", {
        "pmcid": pmcid,
        "rows_accepted": len(accepted_rows),
        "rows_rejected_evidence": n_reject,
        "elapsed_s": round(time.monotonic() - t_article, 2),
        "usage_prompt_gate": gate_reply.usage_prompt,
        "usage_completion_gate": gate_reply.usage_completion,
        "usage_prompt_extract": extract_reply.usage_prompt,
        "usage_completion_extract": extract_reply.usage_completion,
    }))
    return result(pmcid=pmcid, mark=True,
                  rows_tsv=render_rows_tsv(accepted_rows), done=True)

def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)
    cfg = load_config(args.config)

    input_dir  = args.input_dir  or Path(cfg["paths"]["input_dir"])
    output_tsv = args.output_tsv or Path(cfg["paths"]["output_tsv"])
    log_file   = args.log_file   or Path(cfg["paths"]["log_file"])
    evidence_audit_path = output_tsv.with_suffix(output_tsv.suffix + ".evidence.jsonl")

    if not input_dir.is_dir():
        logging.error("input dir not found: %s", input_dir)
        return 2

    extr_cfg = cfg.get("extraction", {}) or {}
    use_guided_json    = bool(extr_cfg.get("use_guided_json", True))
    verify_evidence_on = bool(extr_cfg.get("verify_evidence", True))
    concurrency = args.concurrency if args.concurrency is not None \
        else int(extr_cfg.get("concurrency", 1))
    concurrency = max(1, concurrency)

    section_cfg = SectionConfig.from_dict(cfg["sections"])
    prefilter   = Prefilter.from_config(cfg["prefilter"])
    client      = LLMClient(
        base_url=cfg["server"]["base_url"],
        api_key=cfg["server"]["api_key"],
        model=cfg["server"]["model"],
        timeout_s=float(cfg["server"]["timeout_s"]),
        max_retries=int(cfg["server"]["max_retries"]),
    )
    if not client.ping():
        logging.error("vLLM server is not reachable at %s -- start it first",
                      cfg["server"]["base_url"])
        return 3

    progress = ProgressFile(output_tsv)
    tsv      = TsvAppender(output_tsv, tsv_header())
    jlog     = JsonlLogger(log_file)
    audit    = EvidenceAudit(evidence_audit_path)
    jlog.event("run.start",
               input_dir=str(input_dir),
               output_tsv=str(output_tsv),
               evidence_audit=str(evidence_audit_path),
               use_guided_json=use_guided_json,
               verify_evidence=verify_evidence_on,
               concurrency=concurrency,
               already_done=progress.count)

    _install_signal_handlers()

    all_paths = list(iter_article_paths(input_dir))
    if args.limit is not None:
        all_paths = all_paths[: args.limit]
    logging.warning("found %d candidate articles (resuming, %d already done); concurrency=%d",
                    len(all_paths), progress.count, concurrency)

    gen = cfg["generation"]
    gate_schema    = GATE_JSON_SCHEMA       if use_guided_json else None
    extract_schema = EXTRACTION_JSON_SCHEMA if use_guided_json else None

    stats = {
        "seen": 0, "skipped_resume": 0, "prefilter_skip": 0, "gate_skip": 0,
        "extract_empty": 0, "rows_written": 0, "rows_rejected_evidence": 0, "errors": 0,
    }

    pbar = tqdm(total=len(all_paths), desc="articles", unit="art")

    def apply(res: dict) -> None:
        for name, kw in res["events"]:
            jlog.event(name, **kw)
        for a in res["audit"]:
            audit.record(**a)
        if res["rows_tsv"]:
            tsv.append_block(res["rows_tsv"])
        if res["mark"] and res["pmcid"]:
            progress.mark(res["pmcid"])
        for k, v in res["stats"].items():
            stats[k] = stats.get(k, 0) + v
        stats["seen"] += 1
        if res["done"]:
            pbar.set_postfix(written=stats["rows_written"],
                             ev_rej=stats["rows_rejected_evidence"],
                             gate_skip=stats["gate_skip"])
        pbar.update(1)

    def worker(path: Path) -> dict:
        return process_one(
            path, section_cfg=section_cfg, prefilter=prefilter, client=client,
            gen=gen, gate_schema=gate_schema, extract_schema=extract_schema,
            verify_evidence_on=verify_evidence_on,
        )

    todo: list = []
    for path in all_paths:
        pf = parse_filename(path)
        if pf is None:
            jlog.event("article.bad_filename", path=str(path))
            stats["errors"] += 1
            stats["seen"] += 1
            pbar.update(1)
            continue
        if progress.has(pf[0]):
            stats["skipped_resume"] += 1
            stats["seen"] += 1
            pbar.update(1)
            continue
        todo.append(path)

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            it = iter(todo)
            inflight = set()

            def submit_next() -> bool:
                try:
                    nxt = next(it)
                except StopIteration:
                    return False
                inflight.add(ex.submit(worker, nxt))
                return True

            for _ in range(concurrency):
                if not submit_next():
                    break

            while inflight:
                done, inflight = wait(inflight, return_when=FIRST_COMPLETED)
                for fut in done:
                    try:
                        res = fut.result()
                    except Exception as exc:
                        logging.error("worker crashed: %s", exc)
                        stats["errors"] += 1
                        stats["seen"] += 1
                        pbar.update(1)
                        continue
                    apply(res)
                    if not _shutdown:
                        submit_next()
    finally:
        pbar.close()
        jlog.event("run.end", **stats)
        jlog.close()
        tsv.close()
        audit.close()

    logging.warning("done. stats: %s", stats)
    return 0

if __name__ == "__main__":
    sys.exit(main())
