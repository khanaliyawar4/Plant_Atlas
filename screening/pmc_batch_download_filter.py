#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Set

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import ClientError

BUCKET = "pmc-oa-opendata"
log = logging.getLogger("pmc_batch")

def make_s3():
    return boto3.client(
        "s3",
        config=Config(
            signature_version=UNSIGNED,
            max_pool_connections=64,
            retries={"max_attempts": 5, "mode": "standard"},
            connect_timeout=30,
            read_timeout=120,
        ),
    )

def shard_of(pmcid: str, num_shards: int) -> int:
    return hashlib.md5(pmcid.encode()).digest()[0] % num_shards

def disk_free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / (1024 ** 3)

def _atomic_lock(path: Path) -> bool:
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.close(fd)
        return True
    except FileExistsError:
        return False

def list_all_prefixes(s3, cache_path: Path) -> List[str]:
    STALE_AFTER_S = 300

    if cache_path.exists() and cache_path.stat().st_size > 0:
        log.info("loading prefix cache %s", cache_path)
        with cache_path.open() as fp:
            prefixes = [l.strip() for l in fp if l.strip()]
        log.info("  %d prefixes loaded from cache", len(prefixes))
        return prefixes

    lock = cache_path.with_suffix(".lock")
    part = cache_path.with_suffix(".part")

    while True:
        if _atomic_lock(lock):
            break

        if cache_path.exists() and cache_path.stat().st_size > 0:
            with cache_path.open() as fp:
                return [l.strip() for l in fp if l.strip()]

        try:
            lock_age = time.time() - lock.stat().st_mtime
        except FileNotFoundError:
            continue
        part_age = float("inf")
        if part.exists():
            try:
                part_age = time.time() - part.stat().st_mtime
            except FileNotFoundError:
                pass

        if lock_age > STALE_AFTER_S and part_age > STALE_AFTER_S:
            log.warning(
                "stale lock detected (lock_age=%.0fs, part_age=%.0fs); breaking it",
                lock_age, part_age,
            )
            for p in (lock, part):
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
            continue

        log.info(
            "another process is listing (lock_age=%.0fs, part_age=%.0fs); polling ...",
            lock_age, part_age,
        )
        time.sleep(60)

    try:
        log.info("listing all PMC*/ prefixes in s3://%s/ -- one time, ~15-30 min", BUCKET)
        n = 0
        t0 = time.time()
        with part.open("w") as fp:
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=BUCKET, Delimiter="/"):
                for cp in page.get("CommonPrefixes") or []:
                    p = cp["Prefix"]
                    if p.startswith("PMC") and p.endswith("/"):
                        fp.write(p.rstrip("/") + "\n")
                        n += 1
                fp.flush()
                try:
                    os.utime(lock, None)
                except OSError:
                    pass
                if n and n % 200_000 == 0:
                    log.info("  %d prefixes (%.1f min)", n, (time.time() - t0) / 60)
        part.replace(cache_path)
        log.info("cached %d prefixes to %s (%.1f min)", n, cache_path, (time.time() - t0) / 60)
        with cache_path.open() as fp:
            return [l.strip() for l in fp if l.strip()]
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass

def download_article(s3, pmcid: str, dest_root: Path) -> dict:
    art_dir = dest_root / pmcid
    art_dir.mkdir(parents=True, exist_ok=True)
    out = {"pmcid": pmcid, "txt": False, "xml": False}
    for ext in ("txt", "xml"):
        key = f"{pmcid}/{pmcid}.{ext}"
        try:
            body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            (art_dir / f"{pmcid}.{ext}").write_bytes(body)
            out[ext] = True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            out[f"err_{ext}"] = code or str(e)[:80]
        except Exception as e:
            out[f"err_{ext}"] = str(e)[:120]
    return out

def process_batch(
    s3,
    batch_pmcids: List[str],
    batch_dir: Path,
    output_dir: Path,
    report_path: Path,
    workers: int,
) -> dict:
    if batch_dir.exists():
        shutil.rmtree(batch_dir)
    batch_dir.mkdir(parents=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(download_article, s3, p, batch_dir) for p in batch_pmcids]
        n_txt_ok = n_xml_ok = 0
        for f in as_completed(futures):
            r = f.result()
            n_txt_ok += int(bool(r["txt"]))
            n_xml_ok += int(bool(r["xml"]))
    t_dl = time.time() - t0

    pre_keeps = {p.name for p in output_dir.glob("PMC*.txt")}

    t1 = time.time()
    cmd = [
        "plant-bioeng-filter",
        "--pmc-root", str(batch_dir),
        "--output",   str(output_dir),
        "--report",   str(report_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    t_filt = time.time() - t1

    if proc.returncode != 0:
        log.error("filter exit=%d on %s: %s",
                  proc.returncode, batch_dir.name, proc.stderr[-1500:])
    else:
        tail = [l for l in (proc.stderr or "").splitlines()
                if "Done" in l or "Kept" in l]
        if tail:
            log.info("  filter: %s", tail[-1])

    cur_keeps = {p.name for p in output_dir.glob("PMC*.txt")}
    new_keeps = sorted(cur_keeps - pre_keeps)
    n_xml_copied = 0
    for name in new_keeps:
        pid = name[:-4]
        xml_src = batch_dir / pid / f"{pid}.xml"
        xml_dst = output_dir / f"{pid}.xml"
        if xml_src.is_file() and not xml_dst.exists():
            try:
                shutil.copy2(xml_src, xml_dst)
                n_xml_copied += 1
            except Exception as e:
                log.warning("xml copy %s failed: %s", pid, e)

    shutil.rmtree(batch_dir, ignore_errors=True)

    return {
        "txt_dl": n_txt_ok,
        "xml_dl": n_xml_ok,
        "kept_txt": len(new_keeps),
        "kept_xml": n_xml_copied,
        "filter_rc": proc.returncode,
        "dl_sec": t_dl,
        "filter_sec": t_filt,
    }

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--output",      required=True, type=Path)
    ap.add_argument("--tmp-dir",     required=True, type=Path)
    ap.add_argument("--shard",       type=int, default=0)
    ap.add_argument("--num-shards",  type=int, default=2)
    ap.add_argument("--batch-size",  type=int, default=5000)
    ap.add_argument("--workers",     type=int, default=32)
    ap.add_argument("--prefix-cache",type=Path, default=None)
    ap.add_argument("--manifest",    type=Path, default=None)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    args.output.mkdir(parents=True, exist_ok=True)
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = args.output / "_reports"
    reports_dir.mkdir(exist_ok=True)

    prefix_cache  = args.prefix_cache or (args.output / "_all_prefixes.txt")
    manifest_path = args.manifest     or (args.output / f"_completed_batches_shard{args.shard}.txt")

    log.info("shard=%d/%d  batch_size=%d  workers=%d",
             args.shard, args.num_shards, args.batch_size, args.workers)
    log.info("output  : %s", args.output)
    log.info("tmp_dir : %s   (%.1f GB free)", args.tmp_dir, disk_free_gb(args.tmp_dir))
    log.info("source  : s3://%s/    (per PMC_notes_2026-05-26.txt)", BUCKET)

    stop = {"flag": False}
    def _sig(*_):
        log.warning("signal received -- finishing current batch then exiting.")
        stop["flag"] = True
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT,  _sig)

    s3 = make_s3()

    all_prefixes = list_all_prefixes(s3, prefix_cache)

    my_prefixes = [p for p in all_prefixes if shard_of(p, args.num_shards) == args.shard]
    log.info("my shard owns %d / %d articles", len(my_prefixes), len(all_prefixes))

    completed: Set[str] = set()
    if manifest_path.exists():
        completed = {l.strip() for l in manifest_path.read_text().splitlines() if l.strip()}
    log.info("resuming with %d batches already completed", len(completed))

    manifest_fp = manifest_path.open("a", buffering=1)
    total_proc  = 0
    total_kept  = 0
    total_xml   = 0
    t_run = time.time()

    try:
        for bi in range(0, len(my_prefixes), args.batch_size):
            if stop["flag"]:
                break

            batch_idx = bi // args.batch_size
            batch_id  = f"shard{args.shard}_batch{batch_idx:06d}"
            if batch_id in completed:
                continue

            free_gb = disk_free_gb(args.tmp_dir)
            if free_gb < 3:
                log.error("only %.1f GB free in %s; refusing to start batch %s",
                          free_gb, args.tmp_dir, batch_id)
                break

            batch_pmcids = my_prefixes[bi:bi + args.batch_size]
            batch_dir    = args.tmp_dir / batch_id
            report_path  = reports_dir / f"{batch_id}.csv"

            log.info("=== %s : %d articles ===", batch_id, len(batch_pmcids))
            stats = process_batch(s3, batch_pmcids, batch_dir,
                                  args.output, report_path, args.workers)
            log.info(
                "  dl=%.1fs  filt=%.1fs  txt_dl=%d xml_dl=%d  kept_txt=%d kept_xml=%d",
                stats["dl_sec"], stats["filter_sec"],
                stats["txt_dl"], stats["xml_dl"],
                stats["kept_txt"], stats["kept_xml"],
            )

            manifest_fp.write(batch_id + "\n")
            manifest_fp.flush()
            try:
                os.fsync(manifest_fp.fileno())
            except OSError:
                pass

            total_proc += len(batch_pmcids)
            total_kept += stats["kept_txt"]
            total_xml  += stats["kept_xml"]

            if batch_idx and batch_idx % 10 == 0:
                elapsed = time.time() - t_run
                rate    = total_proc / elapsed if elapsed > 0 else 0
                remain  = len(my_prefixes) - total_proc
                eta_min = remain / max(rate, 1e-6) / 60
                log.info(
                    "PROGRESS  proc=%d/%d (%.1f%%)  kept_txt=%d  kept_xml=%d  rate=%.1f/s  eta=%.1fmin",
                    total_proc, len(my_prefixes),
                    100.0 * total_proc / max(len(my_prefixes), 1),
                    total_kept, total_xml, rate, eta_min,
                )
    finally:
        manifest_fp.close()

    elapsed = time.time() - t_run
    log.info("SHARD %d DONE  processed=%d  kept_txt=%d  kept_xml=%d  elapsed=%.1fmin",
             args.shard, total_proc, total_kept, total_xml, elapsed / 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
