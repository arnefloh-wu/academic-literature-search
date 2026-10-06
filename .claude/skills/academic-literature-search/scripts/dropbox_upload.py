#!/usr/bin/env python3
"""Upload a local folder tree to Dropbox (standard library only).

Reads DROPBOX_ACCESS_TOKEN, or DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET,
from the environment or the skill's .env file. Files up to 150 MB go through
/2/files/upload; larger files use an upload session. Existing files are overwritten only
when their content differs (Dropbox content hash), so re-runs are cheap.

Usage:
    python dropbox_upload.py "topics/<topic>" "/Academic Literature Search/<topic>"
    python dropbox_upload.py "topics/<topic>" "/Academic Literature Search/<topic>" --exclude notion.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from search_sources import load_env, env  # noqa: E402

API = "https://api.dropboxapi.com/2"
CONTENT = "https://content.dropboxapi.com/2"
CHUNK = 8 * 1024 * 1024
SIMPLE_LIMIT = 150 * 1024 * 1024


def token() -> str:
    if env("DROPBOX_ACCESS_TOKEN"):
        return env("DROPBOX_ACCESS_TOKEN")
    if env("DROPBOX_REFRESH_TOKEN") and env("DROPBOX_APP_KEY") and env("DROPBOX_APP_SECRET"):
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token", "refresh_token": env("DROPBOX_REFRESH_TOKEN"),
            "client_id": env("DROPBOX_APP_KEY"), "client_secret": env("DROPBOX_APP_SECRET"),
        }).encode()
        req = urllib.request.Request("https://api.dropboxapi.com/oauth2/token", data=body)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["access_token"]
    raise SystemExit("No Dropbox credentials: set DROPBOX_ACCESS_TOKEN or the refresh-token "
                     "trio in .env (see .env.example).")


def call(tok: str, url: str, arg: dict | None = None, data: bytes | None = None,
         content_api: bool = False) -> dict:
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {tok}")
    if content_api:
        req.add_header("Dropbox-API-Arg", json.dumps(arg))
        req.add_header("Content-Type", "application/octet-stream")
        payload = data or b""
    else:
        req.add_header("Content-Type", "application/json")
        payload = json.dumps(arg or {}).encode()
    try:
        with urllib.request.urlopen(req, data=payload, timeout=120) as resp:
            text = resp.read().decode()
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"Dropbox {e.code} for {url.rsplit('/', 1)[-1]}: {detail}") from e


def content_hash(path: Path) -> str:
    """Dropbox content hash: SHA-256 of the concatenated SHA-256 of 4 MB blocks."""
    block, digests = 4 * 1024 * 1024, []
    with path.open("rb") as f:
        while chunk := f.read(block):
            digests.append(hashlib.sha256(chunk).digest())
    return hashlib.sha256(b"".join(digests)).hexdigest()


def remote_hashes(tok: str, folder: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    try:
        res = call(tok, f"{API}/files/list_folder", {"path": folder, "recursive": True})
    except RuntimeError as e:
        if "not_found" in str(e):
            return hashes
        raise
    while True:
        for entry in res.get("entries", []):
            if entry.get(".tag") == "file":
                hashes[entry["path_lower"]] = entry.get("content_hash", "")
        if not res.get("has_more"):
            return hashes
        res = call(tok, f"{API}/files/list_folder/continue", {"cursor": res["cursor"]})


def ensure_folder(tok: str, folder: str) -> None:
    try:
        call(tok, f"{API}/files/create_folder_v2", {"path": folder, "autorename": False})
    except RuntimeError as e:
        if "conflict" not in str(e):
            raise


def upload(tok: str, local: Path, remote: str) -> None:
    mode = {"path": remote, "mode": "overwrite", "mute": True}
    size = local.stat().st_size
    if size <= SIMPLE_LIMIT:
        call(tok, f"{CONTENT}/files/upload", mode, local.read_bytes(), content_api=True)
        return
    with local.open("rb") as f:
        session = call(tok, f"{CONTENT}/files/upload_session/start", {"close": False},
                       f.read(CHUNK), content_api=True)["session_id"]
        offset = CHUNK
        while True:
            chunk = f.read(CHUNK)
            cursor = {"session_id": session, "offset": offset}
            if len(chunk) < CHUNK:
                call(tok, f"{CONTENT}/files/upload_session/finish",
                     {"cursor": cursor, "commit": mode}, chunk, content_api=True)
                return
            call(tok, f"{CONTENT}/files/upload_session/append_v2",
                 {"cursor": cursor, "close": False}, chunk, content_api=True)
            offset += len(chunk)


def main(argv: list[str] | None = None) -> int:
    load_env()
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("local_dir")
    p.add_argument("remote_dir", help='Dropbox path, e.g. "/Academic Literature Search/<topic>"')
    p.add_argument("--exclude", nargs="*", default=[], help="file names to skip")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    local_root = Path(args.local_dir).resolve()
    if not local_root.is_dir():
        p.error(f"{local_root} is not a directory")
    remote_root = "/" + args.remote_dir.strip("/")
    tok = token()
    existing = remote_hashes(tok, remote_root)
    ensure_folder(tok, remote_root)

    uploaded = skipped = 0
    for path in sorted(local_root.rglob("*")):
        if path.is_dir() or path.name in args.exclude or path.name.startswith("."):
            continue
        rel = path.relative_to(local_root).as_posix()
        remote = f"{remote_root}/{rel}"
        if existing.get(remote.lower()) == content_hash(path):
            skipped += 1
            continue
        parent = remote.rsplit("/", 1)[0]
        if parent != remote_root and not args.dry_run:
            ensure_folder(tok, parent)
        print(f"{'would upload' if args.dry_run else 'upload'} {rel} ({path.stat().st_size:,} B)")
        if not args.dry_run:
            upload(tok, path, remote)
        uploaded += 1
    print(f"{uploaded} uploaded, {skipped} unchanged -> {remote_root}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
