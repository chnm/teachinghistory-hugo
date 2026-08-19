#!/usr/bin/env python3
"""Prepare and run the TeachingHistory.org YouTube video migration.

The safe default is a dry run. Generating and validating a manifest requires
only PyYAML. Uploading additionally requires the Google API client packages in
``utils/youtube-requirements.txt``, OAuth credentials for the TeachingHistory
channel, explicit approval on each manifest row, and ``--confirm-upload``.

Upload state is saved after every successful video. Re-running the command
skips completed upload keys, so a network interruption cannot create duplicate
uploads from the same manifest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    import yaml
except ImportError:  # pragma: no cover - operator setup path
    yaml = None


class LiteralString(str):
    """Marker for readable YAML block scalars."""


if yaml is not None:
    class FrontMatterDumper(yaml.SafeDumper):
        pass

    FrontMatterDumper.add_representer(
        LiteralString,
        lambda dumper, value: dumper.represent_scalar(
            "tag:yaml.org,2002:str", value, style="|"
        ),
    )


REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_ROOT = REPO_ROOT / "teachinghistory-website"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "youtube-migration"
DEFAULT_AUDIT_DIR = (
    REPO_ROOT / "outputs" / "019ff74a-04db-7d31-985d-1327a417a88a"
)
DEFAULT_UPLOAD_QUEUE = DEFAULT_AUDIT_DIR / "video_upload_queue.csv"
DEFAULT_RECONCILIATION = DEFAULT_AUDIT_DIR / "video_reconciliation.csv"
DEFAULT_MANIFEST = DEFAULT_OUTPUT_DIR / "upload-manifest.csv"
DEFAULT_STATE = DEFAULT_OUTPUT_DIR / "upload-state.csv"
DEFAULT_SOURCE_LIST = DEFAULT_OUTPUT_DIR / "server-source-files.txt"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READ_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_SCOPES = [YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READ_SCOPE]
TEACHINGHISTORY_CHANNEL_ID = "UCZBG3EdPK_3O8oUkEE40ZsQ"
APPROVED_VALUES = {"yes", "true", "approved", "1"}
# Drupal node 24171 stores a duplicated second segment at transcript delta 2.
# Its four clip titles align to source transcript positions 1, 2, 4, and 5.
TRANSCRIPT_POSITION_OVERRIDES = {"24171": [1, 2, 4, 5]}
UPLOAD_STATE_FIELDS = [
    "upload_key",
    "youtube_id",
    "youtube_url",
    "uploaded_at",
    "server_filename",
    "drupal_nid",
    "hugo_content_path",
    "clip_index",
    "title",
    "privacy_status",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def front_matter(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit(
            "PyYAML is required. Run: uv pip install -r utils/youtube-requirements.txt"
        )
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    data = yaml.safe_load(text[4:end])
    return data if isinstance(data, dict) else {}


def plain_text(value: str) -> str:
    value = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*_`]+", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def title_prefix(page_url: str) -> str:
    if "/examples-of-historical-thinking/" in page_url:
        return "Examples of Historical Thinking"
    if "/teaching-in-action/" in page_url:
        return "Teaching in Action"
    if "/using-primary-sources/" in page_url:
        return "Using Primary Sources"
    return ""


def proposed_title(row: dict[str, str]) -> tuple[str, str]:
    prefix = title_prefix(row["canonical_page_url"])
    components = [prefix, row["page_title"], row["clip_title"]]
    full_title = " - ".join(component.strip() for component in components if component.strip())
    full_title = full_title or row["asset_name"]
    if len(full_title) <= 100:
        return full_title, ""

    # Preserve the most specific information (page and clip) when the channel's
    # usual series prefix would push a title beyond YouTube's 100-character cap.
    compact = " - ".join(
        component.strip()
        for component in [row["page_title"], row["clip_title"]]
        if component.strip()
    )
    if len(compact) <= 100:
        return compact, f"title shortened from {len(full_title)} characters by removing series prefix"

    clip = row["clip_title"].strip()
    if clip and len(clip) < 94:
        available = 100 - len(clip) - 3
        page = row["page_title"].strip()
        page = page if len(page) <= available else page[: max(1, available - 1)].rstrip() + "…"
        compact = f"{page} - {clip}"
    else:
        compact = compact[:99].rstrip() + "…"
    return compact, f"title shortened from {len(full_title)} characters to fit YouTube's limit"


def upload_key(row: dict[str, str]) -> str:
    identity = ":".join(
        [row["drupal_nid"], row["asset_name"].lower(), row["clip_index"]]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def metadata_description(summary: str, url: str) -> str:
    summary = plain_text(summary)
    return f"{summary}\n\n{url}" if summary else url


def manifest_fields() -> list[str]:
    return [
        "approved",
        "upload_key",
        "server_filename",
        "drupal_nid",
        "hugo_content_path",
        "canonical_page_url",
        "teachinghistory_url",
        "clip_index",
        "asset_name",
        "clip_title",
        "title",
        "description",
        "tags",
        "category_id",
        "privacy_status",
        "metadata_warnings",
        "requires_metadata_review",
        "source_status",
        "youtube_id",
        "youtube_url",
        "upload_status",
        "operator_notes",
    ]


def command_manifest(args: argparse.Namespace) -> int:
    queue = read_csv(args.upload_queue)
    existing = {
        row["upload_key"]: row
        for row in read_csv(args.manifest)
    } if args.manifest.exists() else {}
    rows: list[dict[str, Any]] = []
    for source in queue:
        content_path = SITE_ROOT / "content" / source["hugo_content_path"]
        metadata = front_matter(content_path) if content_path.is_file() else {}
        title, title_warning = proposed_title(source)
        description = metadata_description(
            str(metadata.get("summary", "")), source["teachinghistory_url"]
        )
        warnings = []
        if title_warning:
            warnings.append(title_warning)
        if not metadata.get("summary"):
            warnings.append("Hugo summary is missing; description contains only the URL")
        if not source["server_filename"]:
            warnings.append("server filename is missing")
        key = upload_key(source)
        prior = existing.get(key, {})
        preserve_reviewed_metadata = bool(
            prior.get("operator_notes")
            or prior.get("approved", "").strip().lower() in APPROVED_VALUES
        )
        rows.append(
            {
                "approved": prior.get("approved", ""),
                "upload_key": key,
                "server_filename": source["server_filename"],
                "drupal_nid": source["drupal_nid"],
                "hugo_content_path": source["hugo_content_path"],
                "canonical_page_url": source["canonical_page_url"],
                "teachinghistory_url": source["teachinghistory_url"],
                "clip_index": source["clip_index"],
                "asset_name": source["asset_name"],
                "clip_title": source["clip_title"],
                "title": prior.get("title", title) if preserve_reviewed_metadata else title,
                "description": prior.get("description", description) if preserve_reviewed_metadata else description,
                "tags": prior.get("tags", source["asset_name"]) if preserve_reviewed_metadata else source["asset_name"],
                "category_id": prior.get("category_id", "27") if preserve_reviewed_metadata else "27",
                "privacy_status": prior.get("privacy_status", args.privacy_status) if preserve_reviewed_metadata else args.privacy_status,
                "metadata_warnings": " | ".join(warnings),
                "requires_metadata_review": "Yes" if warnings else "No",
                "source_status": source["migration_source_status"],
                "youtube_id": prior.get("youtube_id", ""),
                "youtube_url": prior.get("youtube_url", ""),
                "upload_status": prior.get("upload_status", "Not started"),
                "operator_notes": prior.get("operator_notes", ""),
            }
        )
    rows.sort(
        key=lambda row: (
            row["canonical_page_url"],
            int(row["clip_index"]) if str(row["clip_index"]).isdigit() else 9999,
        )
    )
    write_csv(args.manifest, rows, manifest_fields())
    args.source_list.parent.mkdir(parents=True, exist_ok=True)
    args.source_list.write_text(
        "\n".join(row["server_filename"] for row in rows) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "manifest": str(args.manifest),
        "server_source_list": str(args.source_list),
        "rows": len(rows),
        "pages": len({row["hugo_content_path"] for row in rows}),
        "metadata_warning_rows": sum(bool(row["metadata_warnings"]) for row in rows),
        "approved_rows_preserved": sum(
            str(row["approved"]).strip().lower() in APPROVED_VALUES for row in rows
        ),
    }, indent=2))
    return 0


def validate_manifest(
    manifest_path: Path,
    video_root: Path | None,
    require_approved: bool,
) -> tuple[list[dict[str, str]], list[str]]:
    rows = read_csv(manifest_path)
    errors: list[str] = []
    keys: set[str] = set()
    filenames: set[str] = set()
    for line, row in enumerate(rows, start=2):
        key = row["upload_key"]
        if key in keys:
            errors.append(f"row {line}: duplicate upload_key {key}")
        keys.add(key)
        filename = row["server_filename"].casefold()
        if filename in filenames:
            errors.append(f"row {line}: duplicate server filename {row['server_filename']}")
        filenames.add(filename)
        if len(row["title"]) > 100:
            errors.append(f"row {line}: title exceeds 100 characters")
        if not row["description"].strip():
            errors.append(f"row {line}: description is empty")
        if row["privacy_status"] not in {"private", "unlisted", "public"}:
            errors.append(f"row {line}: invalid privacy status")
        if require_approved and row["approved"].strip().lower() not in APPROVED_VALUES:
            errors.append(f"row {line}: not approved")
        if video_root is not None:
            source = video_root / row["server_filename"]
            if not source.is_file():
                errors.append(f"row {line}: source file not found: {source}")
            elif source.stat().st_size == 0:
                errors.append(f"row {line}: source file is empty: {source}")
    return rows, errors


def command_validate(args: argparse.Namespace) -> int:
    rows, errors = validate_manifest(
        args.manifest, args.video_root, args.require_approved
    )
    print(json.dumps({
        "manifest": str(args.manifest),
        "rows": len(rows),
        "video_root": str(args.video_root) if args.video_root else "not checked",
        "errors": errors,
    }, indent=2))
    return 1 if errors else 0


def load_upload_state(path: Path) -> list[dict[str, str]]:
    return read_csv(path) if path.exists() else []


def youtube_id_from_url(value: str) -> str:
    """Return a canonical 11-character YouTube ID from a supported URL."""
    if not value.strip():
        return ""
    parsed = urlparse(value.strip())
    hostname = (parsed.hostname or "").lower()
    youtube_id = ""
    if hostname in {"youtu.be", "www.youtu.be"}:
        youtube_id = parsed.path.strip("/").split("/", 1)[0]
    elif hostname == "youtube.com" or hostname.endswith(".youtube.com"):
        if parsed.path.rstrip("/") == "/watch":
            youtube_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"embed", "live", "shorts"}:
                youtube_id = parts[1]
    return youtube_id if re.fullmatch(r"[A-Za-z0-9_-]{11}", youtube_id) else ""


def manifest_youtube_id(row: dict[str, str]) -> str:
    """Use an explicit ID when valid, otherwise derive it from youtube_url."""
    youtube_id = row.get("youtube_id", "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", youtube_id):
        return youtube_id
    return youtube_id_from_url(row.get("youtube_url", ""))


def current_hugo_paths_by_nid() -> dict[str, str]:
    """Index current content paths so plans survive filename cleanup."""
    paths: dict[str, str] = {}
    duplicates: set[str] = set()
    pattern = re.compile(r"(?m)^drupal_nid:\s*['\"]?(\d+)['\"]?\s*$")
    content_root = SITE_ROOT / "content"
    for path in content_root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        delimiter = text.find("\n---\n", 4)
        match = pattern.search(text, 4, delimiter if delimiter != -1 else len(text))
        if not match:
            continue
        nid = match.group(1)
        relative = str(path.relative_to(content_root))
        if nid in paths and paths[nid] != relative:
            duplicates.add(nid)
        paths[nid] = relative
    if duplicates:
        raise ValueError(
            "duplicate drupal_nid values in Hugo content: " + ", ".join(sorted(duplicates))
        )
    return paths


def save_upload_state(path: Path, rows: list[dict[str, str]]) -> None:
    write_csv(path, rows, UPLOAD_STATE_FIELDS)


def youtube_service(client_secrets: Path, token_file: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as error:  # pragma: no cover - operator setup path
        raise SystemExit(
            "Google API dependencies are missing. Run: "
            "uv pip install -r utils/youtube-requirements.txt"
        ) from error

    credentials = None
    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_file), YOUTUBE_SCOPES
        )
        if not credentials.has_scopes(YOUTUBE_SCOPES):
            credentials = None
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets), YOUTUBE_SCOPES
        )
        credentials = flow.run_local_server(port=0)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=credentials)


def authenticated_channel(service) -> dict[str, str]:
    response = service.channels().list(part="id,snippet", mine=True).execute()
    items = response.get("items", [])
    if len(items) != 1:
        raise RuntimeError(
            f"Expected one authenticated YouTube channel, received {len(items)}"
        )
    return {
        "channel_id": str(items[0].get("id", "")),
        "channel_title": str(items[0].get("snippet", {}).get("title", "")),
    }


def command_auth_check(args: argparse.Namespace) -> int:
    service = youtube_service(args.client_secrets, args.token_file)
    channel = authenticated_channel(service)
    channel["matches_expected_channel"] = str(
        channel["channel_id"] == args.expected_channel_id
    ).lower()
    print(json.dumps(channel, indent=2))
    return 0 if channel["channel_id"] == args.expected_channel_id else 1


def resumable_upload(request, max_retries: int) -> dict[str, Any]:
    try:
        from googleapiclient.errors import HttpError
    except ImportError as error:  # pragma: no cover
        raise SystemExit("Google API dependencies are missing") from error

    response = None
    retry = 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as error:
            if error.resp.status not in {500, 502, 503, 504}:
                raise
            retry += 1
            if retry > max_retries:
                raise
            time.sleep(random.uniform(0, 2**retry))
        except (OSError, TimeoutError):
            retry += 1
            if retry > max_retries:
                raise
            time.sleep(random.uniform(0, 2**retry))
    return response


def command_upload(args: argparse.Namespace) -> int:
    if not args.confirm_upload:
        raise SystemExit("Refusing to upload without --confirm-upload")
    rows, errors = validate_manifest(args.manifest, args.video_root, False)
    if errors:
        print("Manifest validation failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as error:  # pragma: no cover - operator setup path
        raise SystemExit(
            "Google API dependencies are missing. Run: "
            "uv pip install -r utils/youtube-requirements.txt"
        ) from error

    approved = [
        row for row in rows
        if row["approved"].strip().lower() in APPROVED_VALUES
    ]
    if not approved:
        raise SystemExit("No manifest rows are approved for upload")
    state = load_upload_state(args.state)
    completed = {row["upload_key"] for row in state if row.get("youtube_id")}
    pending = [row for row in approved if row["upload_key"] not in completed]
    if args.max_uploads is not None:
        pending = pending[: args.max_uploads]
    if not pending:
        print("No approved uploads remain.")
        return 0

    service = youtube_service(args.client_secrets, args.token_file)
    channel = authenticated_channel(service)
    if channel["channel_id"] != args.expected_channel_id:
        raise SystemExit(
            "Refusing to upload: authenticated channel "
            f"{channel['channel_title']} ({channel['channel_id']}) does not match "
            f"expected TeachingHistory channel {args.expected_channel_id}"
        )
    print(
        f"Authenticated channel: {channel['channel_title']} ({channel['channel_id']})"
    )
    for index, row in enumerate(pending, start=1):
        tags = [tag.strip() for tag in row["tags"].split(",") if tag.strip()]
        body = {
            "snippet": {
                "title": row["title"],
                "description": row["description"],
                "tags": tags,
                "categoryId": row["category_id"],
            },
            "status": {"privacyStatus": row["privacy_status"]},
        }
        source = args.video_root / row["server_filename"]
        print(f"[{index}/{len(pending)}] Uploading {source.name}: {row['title']}")
        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=MediaFileUpload(
                str(source), chunksize=8 * 1024 * 1024, resumable=True
            ),
        )
        response = resumable_upload(request, args.max_retries)
        youtube_id = response.get("id", "")
        if not youtube_id:
            raise RuntimeError(f"Upload response did not include an ID: {response}")
        state.append(
            {
                "upload_key": row["upload_key"],
                "youtube_id": youtube_id,
                "youtube_url": f"https://www.youtube.com/watch?v={youtube_id}",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "server_filename": row["server_filename"],
                "drupal_nid": row["drupal_nid"],
                "hugo_content_path": row["hugo_content_path"],
                "clip_index": row["clip_index"],
                "title": row["title"],
                "privacy_status": row["privacy_status"],
            }
        )
        save_upload_state(args.state, state)
        print(f"  uploaded https://www.youtube.com/watch?v={youtube_id}")
    return 0


def command_hugo_plan(args: argparse.Namespace) -> int:
    reconciliation = read_csv(args.reconciliation)
    current_paths = current_hugo_paths_by_nid()
    state = {
        row["upload_key"]: row for row in load_upload_state(args.state)
    }
    upload_manifest = {
        row["upload_key"]: row for row in read_csv(args.manifest)
    } if args.manifest.exists() else {}
    new_ids_by_clip: dict[tuple[str, str], str] = {}
    for key, row in upload_manifest.items():
        state_id = manifest_youtube_id(state.get(key, {}))
        youtube_id = state_id or manifest_youtube_id(row)
        if youtube_id:
            new_ids_by_clip[(row["drupal_nid"], row["clip_index"])] = youtube_id
    plan: list[dict[str, str]] = []
    for row in reconciliation:
        if row["hugo_present"] != "true":
            continue
        youtube_id = row["youtube_ids"].split(" | ")[0] if row["youtube_ids"] else ""
        source = "existing_youtube_match" if youtube_id else ""
        if not youtube_id:
            youtube_id = new_ids_by_clip.get((row["drupal_nid"], row["clip_index"]), "")
            source = "new_upload" if youtube_id else "missing_upload"
        content_path = row["hugo_content_path"]
        if not (SITE_ROOT / "content" / content_path).is_file():
            content_path = current_paths.get(row["drupal_nid"], content_path)
        plan.append({
            "hugo_content_path": content_path,
            "drupal_nid": row["drupal_nid"],
            "clip_index": row["clip_index"],
            "asset_name": row["asset_name"],
            "youtube_id": youtube_id,
            "id_source": source,
            "transcript_present_live": row.get("transcript_present_live", ""),
        })
    fields = [
        "hugo_content_path", "drupal_nid", "clip_index", "asset_name",
        "youtube_id", "id_source", "transcript_present_live",
    ]
    assignments: dict[str, list[str]] = {}
    clip_keys: set[tuple[str, str]] = set()
    duplicate_clips: list[str] = []
    for row in plan:
        clip_key = (row["hugo_content_path"], row["clip_index"])
        if clip_key in clip_keys:
            duplicate_clips.append(f"{clip_key[0]}#{clip_key[1]}")
        clip_keys.add(clip_key)
        if row["youtube_id"]:
            assignments.setdefault(row["youtube_id"], []).append(
                f"{row['hugo_content_path']}#{row['clip_index']}"
            )
    duplicate_ids = {
        youtube_id: clips
        for youtube_id, clips in assignments.items()
        if len(clips) > 1
    }
    if duplicate_clips or duplicate_ids:
        raise ValueError(json.dumps({
            "duplicate_hugo_clips": duplicate_clips,
            "duplicate_youtube_assignments": duplicate_ids,
        }, indent=2))
    write_csv(args.hugo_plan, plan, fields)
    print(json.dumps({
        "hugo_plan": str(args.hugo_plan),
        "current_hugo_clips": len(plan),
        "existing_youtube_ids": sum(row["id_source"] == "existing_youtube_match" for row in plan),
        "new_upload_ids": sum(row["id_source"] == "new_upload" for row in plan),
        "missing_ids": sum(not row["youtube_id"] for row in plan),
    }, indent=2))
    return 0


def normalized_asset(value: str) -> str:
    value = value.replace("\\_", "_")
    stem = Path(value.split("?", 1)[0]).stem.lower()
    return re.sub(r"[^a-z0-9]+", "", stem)


def normalized_transcript_positions(
    nid: str, source_clips: dict[int, str]
) -> dict[int, str]:
    positions = TRANSCRIPT_POSITION_OVERRIDES.get(nid)
    if not positions:
        return source_clips
    return {
        clip_index: source_clips[source_index]
        for clip_index, source_index in enumerate(positions, start=1)
        if source_index in source_clips
    }


def sanitize_transcript_markdown(value: str) -> str:
    """Normalize legacy Unicode separators before serializing YAML scalars."""
    return (
        value.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u0085", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
    )


def load_drupal_transcripts(sql_path: Path) -> dict[str, dict[int, str]]:
    """Read ordered per-clip transcripts from the Drupal transcript table."""
    from drupal_to_hugo import parse_text_field_insert, transcript_html_to_md

    buffer: list[str] = []
    active = False
    with sql_path.open(encoding="utf-8", errors="ignore") as source:
        for line in source:
            if line.startswith("INSERT INTO `node__field_transcript_text`"):
                active = True
                buffer = [line]
                if line.rstrip().endswith(";"):
                    break
                continue
            if active:
                buffer.append(line)
                if line.rstrip().endswith(";"):
                    break
    if not buffer or not buffer[-1].rstrip().endswith(";"):
        raise ValueError(f"Drupal transcript table not found or incomplete: {sql_path}")

    fields: dict[int, dict[str, Any]] = {}
    parse_text_field_insert(buffer, fields, "field_transcript_text")
    transcripts: dict[str, dict[int, str]] = {}
    for nid, node_fields in fields.items():
        items = node_fields.get("field_transcript_text_items", [])
        clips: dict[int, str] = {}
        for index, item in enumerate(sorted(items, key=lambda value: value["delta"]), start=1):
            markdown = sanitize_transcript_markdown(
                transcript_html_to_md([item])
            ).strip()
            if markdown:
                clips[index] = markdown
        if clips:
            nid_text = str(nid)
            transcripts[nid_text] = normalized_transcript_positions(nid_text, clips)
    return transcripts


def load_live_transcripts(
    nids: set[str],
    base_url: str,
    cache_dir: Path,
) -> tuple[dict[str, dict[int, str]], list[str]]:
    """Fetch current Drupal transcript arrays, caching raw JSON outside Git."""
    from drupal_to_hugo import transcript_html_to_md
    from reconcile_videos import fetch_node

    cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(nid: str) -> tuple[str, dict[str, Any] | None, str]:
        cache_path = cache_dir / f"node-{nid}.json"
        if cache_path.is_file():
            try:
                return nid, json.loads(cache_path.read_text(encoding="utf-8")), ""
            except (OSError, json.JSONDecodeError):
                pass
        result = fetch_node(nid, base_url, timeout=25, attempts=2)
        data = result.get("data")
        if not isinstance(data, dict):
            return nid, None, str(result.get("error") or result.get("http_status"))
        temporary = cache_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temporary.replace(cache_path)
        return nid, data, ""

    transcripts: dict[str, dict[int, str]] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(nids)))) as executor:
        futures = {executor.submit(fetch, nid): nid for nid in sorted(nids)}
        for future in as_completed(futures):
            nid, data, error = future.result()
            if error or data is None:
                errors.append(f"nid {nid}: {error or 'no JSON data'}")
                continue
            values = data.get("field_transcript_text") or []
            clips: dict[int, str] = {}
            for index, item in enumerate(values if isinstance(values, list) else [], start=1):
                if not isinstance(item, dict) or not item.get("value"):
                    continue
                markdown = sanitize_transcript_markdown(
                    transcript_html_to_md([
                        {"delta": index - 1, "value": str(item["value"])}
                    ])
                ).strip()
                if markdown:
                    clips[index] = markdown
            if clips:
                transcripts[nid] = normalized_transcript_positions(nid, clips)
    return transcripts, sorted(errors)


def remove_combined_transcript(text: str) -> str:
    """Remove the old combined Transcript section after per-clip migration."""
    delimiter = text.find("\n---\n", 4)
    if delimiter == -1:
        return text
    body_start = delimiter + len("\n---\n")
    body = text[body_start:]
    heading = re.search(r"(?m)^## Transcript\s*$", body)
    if not heading:
        return text
    following = body[heading.end():]
    next_heading = re.search(r"(?m)^## (?!Transcript\s*$).+$", following)
    section_end = heading.end() + (next_heading.start() if next_heading else len(following))
    updated_body = body[:heading.start()].rstrip()
    suffix = body[section_end:].lstrip("\n")
    if suffix:
        updated_body += "\n\n" + suffix
    updated_body = updated_body.rstrip()
    return text[:body_start] + (updated_body + "\n" if updated_body else "")


def replace_video_block(
    path: Path,
    clip_rows: list[dict[str, str]],
    transcripts_by_index: dict[int, str] | None = None,
) -> tuple[str, list[str]]:
    if yaml is None:
        raise SystemExit(
            "PyYAML is required. Run: uv pip install -r utils/youtube-requirements.txt"
        )
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"front matter not found: {path}")
    delimiter = text.find("\n---\n", 4)
    if delimiter == -1:
        raise ValueError(f"front matter closing delimiter not found: {path}")
    metadata_text = text[4:delimiter]
    start_match = re.search(r"(?m)^videos:\s*\n", metadata_text)
    if not start_match:
        return convert_body_videos(
            path, text, metadata_text, delimiter, clip_rows, transcripts_by_index
        )
    block_start = start_match.start()
    following = metadata_text[start_match.end():]
    next_key = re.search(r"(?m)^(?=[A-Za-z_][A-Za-z0-9_-]*:\s*)", following)
    block_end = start_match.end() + (next_key.start() if next_key else len(following))
    block = metadata_text[block_start:block_end]
    parsed = yaml.safe_load(block)
    videos = parsed.get("videos", []) if isinstance(parsed, dict) else []
    if not isinstance(videos, list):
        raise ValueError(f"videos block is not a list: {path}")

    by_index = {int(row["clip_index"]): row for row in clip_rows}
    if len(videos) != len(clip_rows):
        raise ValueError(
            f"video count mismatch for {path}: front matter={len(videos)}, plan={len(clip_rows)}"
        )
    notes: list[str] = []
    migrated: list[dict[str, Any]] = []
    for index, video in enumerate(videos, start=1):
        if not isinstance(video, dict):
            raise ValueError(f"video {index} is not an object: {path}")
        planned = by_index.get(index)
        if not planned or not planned["youtube_id"]:
            raise ValueError(f"YouTube ID missing for video {index}: {path}")
        source_asset = normalized_asset(str(video.get("src", "")))
        planned_asset = normalized_asset(planned["asset_name"])
        if source_asset and planned_asset and source_asset != planned_asset:
            notes.append(
                f"clip {index} asset alias: {source_asset} -> {planned_asset}"
            )
        replacement: dict[str, Any] = {"youtube_id": planned["youtube_id"]}
        for key, value in video.items():
            if key not in {"src", "youtube_id", "transcript"}:
                replacement[key] = value
        transcript = (transcripts_by_index or {}).get(index, "")
        if transcript:
            replacement["transcript"] = LiteralString(transcript)
        migrated.append(replacement)

    rendered = yaml.dump(
        {"videos": migrated},
        Dumper=FrontMatterDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
    if not rendered.endswith("\n"):
        rendered += "\n"
    updated_metadata = metadata_text[:block_start] + rendered + metadata_text[block_end:]
    updated = text[:4] + updated_metadata + text[delimiter:]
    if transcripts_by_index:
        updated = remove_combined_transcript(updated)
    return updated, notes


def convert_body_videos(
    path: Path,
    text: str,
    metadata_text: str,
    delimiter: int,
    clip_rows: list[dict[str, str]],
    transcripts_by_index: dict[int, str] | None = None,
) -> tuple[str, list[str]]:
    """Promote legacy Markdown body video links into structured front matter."""
    body_start = delimiter + len("\n---\n")
    body = text[body_start:]
    linked_pattern = re.compile(
        r"\[!\[(?P<title>[^]]*)\]\((?P<thumb>[^)]+)\)\]\((?P<src>[^)]+)\)"
    )
    linked = list(linked_pattern.finditer(body))
    extracted: list[dict[str, str]] = []
    if linked:
        extracted = [
            {
                "title": match.group("title").strip(),
                "thumb": match.group("thumb").replace("\\_", "_"),
                "src": match.group("src").replace("\\_", "_"),
            }
            for match in linked
        ]
        body = linked_pattern.sub("", body)
        for video in extracted:
            escaped_src = video["src"].replace("_", r"\_")
            for variant in {video["src"], escaped_src}:
                body = re.sub(
                    rf"(?m)^[ \t]*{re.escape(variant)}[ \t]*$\n?", "", body
                )
    else:
        source_match = re.search(
            r"(?m)^\s*(?P<src>\S+\.(?:mp4|m4v|mov|webm|ogv))\s*$",
            body,
            re.IGNORECASE,
        )
        if source_match:
            page_metadata = yaml.safe_load(metadata_text) or {}
            extracted = [{
                "title": str(page_metadata.get("title", "Video")),
                "thumb": "",
                "src": source_match.group("src").replace("\\_", "_"),
            }]
            body = body[:source_match.start()] + body[source_match.end():]
    if not extracted:
        raise ValueError(f"videos block and body video markup not found: {path}")
    if len(extracted) != len(clip_rows):
        raise ValueError(
            f"body video count mismatch for {path}: body={len(extracted)}, plan={len(clip_rows)}"
        )

    body = re.sub(r"(?m)^\s*video/(?:mp4|quicktime|webm|ogg)\s*$", "", body, count=1)
    body = re.sub(r"\A(?:[ \t]*(?:\r?\n)){2,}", "\n", body)
    by_index = {int(row["clip_index"]): row for row in clip_rows}
    migrated: list[dict[str, Any]] = []
    notes = ["promoted legacy body video markup to videos front matter"]
    for index, video in enumerate(extracted, start=1):
        planned = by_index.get(index)
        if not planned or not planned["youtube_id"]:
            raise ValueError(f"YouTube ID missing for body video {index}: {path}")
        source_asset = normalized_asset(video["src"])
        planned_asset = normalized_asset(planned["asset_name"])
        if source_asset and planned_asset and source_asset != planned_asset:
            notes.append(
                f"clip {index} asset alias: {source_asset} -> {planned_asset}"
            )
        item: dict[str, Any] = {
            "youtube_id": planned["youtube_id"],
            "title": video["title"] or planned["asset_name"],
        }
        if video["thumb"]:
            item["thumb"] = video["thumb"]
        transcript = (transcripts_by_index or {}).get(index, "")
        if transcript:
            item["transcript"] = LiteralString(transcript)
        migrated.append(item)
    rendered = yaml.dump(
        {"videos": migrated},
        Dumper=FrontMatterDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
    updated_metadata = metadata_text.rstrip() + "\n" + rendered
    updated = "---\n" + updated_metadata + "---\n" + body
    if transcripts_by_index:
        updated = remove_combined_transcript(updated)
    return updated, notes


def command_apply_hugo(args: argparse.Namespace) -> int:
    plan = read_csv(args.hugo_plan)
    missing = [row for row in plan if not row["youtube_id"]]
    if missing:
        print(
            f"Refusing to apply: {len(missing)} of {len(plan)} Hugo clips still lack YouTube IDs.",
            file=sys.stderr,
        )
        return 1
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in plan:
        grouped.setdefault(row["hugo_content_path"], []).append(row)

    transcripts = load_drupal_transcripts(args.drupal_sql) if args.drupal_sql else {}
    transcript_fetch_errors: list[str] = []
    if args.live_base_url:
        if not args.transcript_cache:
            raise SystemExit("--transcript-cache is required with --live-base-url")
        missing_nids = {
            rows[0]["drupal_nid"]
            for rows in grouped.values()
            if rows[0]["drupal_nid"] not in transcripts
        }
        live_transcripts, transcript_fetch_errors = load_live_transcripts(
            missing_nids, args.live_base_url, args.transcript_cache
        )
        transcripts.update(live_transcripts)

    changes: list[tuple[Path, str, list[str]]] = []
    errors: list[str] = []
    clips_without_transcripts: list[str] = []
    unused_transcripts: list[str] = []
    clips_with_transcripts = 0
    for relative_path, rows in sorted(grouped.items()):
        path = SITE_ROOT / "content" / relative_path
        try:
            nid = rows[0]["drupal_nid"]
            page_transcripts = transcripts.get(nid, {})
            planned_indexes = {int(row["clip_index"]) for row in rows}
            clips_with_transcripts += len(planned_indexes & page_transcripts.keys())
            clips_without_transcripts.extend(
                f"{relative_path}#{row['clip_index']}"
                for row in rows
                if int(row["clip_index"]) not in page_transcripts
            )
            unused_transcripts.extend(
                f"{relative_path}#{index}"
                for index in sorted(page_transcripts.keys() - planned_indexes)
            )
            required_transcripts = {
                int(row["clip_index"])
                for row in rows
                if row.get("transcript_present_live") == "true"
            }
            missing_required = sorted(required_transcripts - page_transcripts.keys())
            if missing_required:
                raise ValueError(
                    f"required Drupal transcripts missing for {path}: clips {missing_required}"
                )
            updated, notes = replace_video_block(path, rows, page_transcripts)
            if updated != path.read_text(encoding="utf-8"):
                changes.append((path, updated, notes))
        except (OSError, ValueError) as error:
            errors.append(str(error))
    if errors:
        print("Hugo migration validation failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1

    print(json.dumps({
        "hugo_clips": len(plan),
        "content_files": len(grouped),
        "files_that_would_change": len(changes),
        "clips_with_transcripts": clips_with_transcripts,
        "clips_without_transcripts": clips_without_transcripts,
        "unused_transcripts": unused_transcripts,
        "transcript_fetch_errors": transcript_fetch_errors,
        "asset_alias_notes": [
            f"{path.relative_to(SITE_ROOT)}: {note}"
            for path, _, notes in changes for note in notes
        ],
        "mode": "apply" if args.confirm_apply else "dry-run",
    }, indent=2))
    if not args.confirm_apply:
        print("Dry run only. Re-run with --confirm-apply after reviewing the plan.")
        return 0
    for path, updated, _ in changes:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(updated, encoding="utf-8")
        os.replace(temporary, path)
    return 0


def command_validate_hugo(args: argparse.Namespace) -> int:
    """Verify the applied plan against structured Hugo video records."""
    plan = read_csv(args.hugo_plan)
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in plan:
        grouped.setdefault(row["hugo_content_path"], []).append(row)

    errors: list[str] = []
    transcript_count = 0
    for relative_path, rows in sorted(grouped.items()):
        path = SITE_ROOT / "content" / relative_path
        if not path.is_file():
            errors.append(f"content file missing: {relative_path}")
            continue
        metadata = front_matter(path)
        videos = metadata.get("videos") or []
        if not isinstance(videos, list):
            errors.append(f"videos is not a list: {relative_path}")
            continue
        rows.sort(key=lambda row: int(row["clip_index"]))
        if len(videos) != len(rows):
            errors.append(
                f"video count mismatch: {relative_path} expected={len(rows)} actual={len(videos)}"
            )
            continue
        for index, (video, row) in enumerate(zip(videos, rows), start=1):
            if not isinstance(video, dict):
                errors.append(f"video {index} is not an object: {relative_path}")
                continue
            if video.get("youtube_id") != row["youtube_id"]:
                errors.append(
                    f"YouTube ID mismatch: {relative_path}#{index} "
                    f"expected={row['youtube_id']} actual={video.get('youtube_id', '')}"
                )
            if video.get("src"):
                errors.append(f"obsolete local video source remains: {relative_path}#{index}")
            if video.get("transcript"):
                transcript_count += 1
        text = path.read_text(encoding="utf-8")
        if any(isinstance(video, dict) and video.get("transcript") for video in videos):
            delimiter = text.find("\n---\n", 4)
            body = text[delimiter + 5:] if delimiter != -1 else text
            if re.search(r"(?m)^## Transcript\s*$", body):
                errors.append(f"combined transcript section remains: {relative_path}")

    print(json.dumps({
        "hugo_plan": str(args.hugo_plan),
        "content_files": len(grouped),
        "video_records": len(plan),
        "transcript_records": transcript_count,
        "errors": errors,
    }, indent=2))
    return 1 if errors else 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    manifest = commands.add_parser("manifest", help="Generate the metadata review manifest")
    manifest.add_argument("--upload-queue", type=Path, default=DEFAULT_UPLOAD_QUEUE)
    manifest.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    manifest.add_argument("--source-list", type=Path, default=DEFAULT_SOURCE_LIST)
    manifest.add_argument(
        "--privacy-status", choices=["private", "unlisted", "public"], default="unlisted"
    )
    manifest.set_defaults(function=command_manifest)

    validate = commands.add_parser("validate", help="Validate metadata and optional source files")
    validate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    validate.add_argument("--video-root", type=Path)
    validate.add_argument("--require-approved", action="store_true")
    validate.set_defaults(function=command_validate)

    auth_check = commands.add_parser(
        "auth-check", help="Authorize and verify the TeachingHistory channel"
    )
    auth_check.add_argument("--client-secrets", type=Path, required=True)
    auth_check.add_argument("--token-file", type=Path, required=True)
    auth_check.add_argument(
        "--expected-channel-id", default=TEACHINGHISTORY_CHANNEL_ID
    )
    auth_check.set_defaults(function=command_auth_check)

    upload = commands.add_parser("upload", help="Upload explicitly approved manifest rows")
    upload.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    upload.add_argument("--state", type=Path, default=DEFAULT_STATE)
    upload.add_argument("--video-root", type=Path, required=True)
    upload.add_argument("--client-secrets", type=Path, required=True)
    upload.add_argument("--token-file", type=Path, required=True)
    upload.add_argument(
        "--expected-channel-id", default=TEACHINGHISTORY_CHANNEL_ID
    )
    upload.add_argument("--max-uploads", type=int)
    upload.add_argument("--max-retries", type=int, default=8)
    upload.add_argument("--confirm-upload", action="store_true")
    upload.set_defaults(function=command_upload)

    hugo_plan = commands.add_parser(
        "hugo-plan", help="Combine existing and newly uploaded IDs for Hugo"
    )
    hugo_plan.add_argument("--reconciliation", type=Path, default=DEFAULT_RECONCILIATION)
    hugo_plan.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    hugo_plan.add_argument("--state", type=Path, default=DEFAULT_STATE)
    hugo_plan.add_argument(
        "--hugo-plan", type=Path, default=DEFAULT_OUTPUT_DIR / "hugo-video-plan.csv"
    )
    hugo_plan.set_defaults(function=command_hugo_plan)

    apply_hugo = commands.add_parser(
        "apply-hugo", help="Replace local MP4 references after all IDs are available"
    )
    apply_hugo.add_argument(
        "--hugo-plan", type=Path, default=DEFAULT_OUTPUT_DIR / "hugo-video-plan.csv"
    )
    apply_hugo.add_argument(
        "--drupal-sql", type=Path,
        help="Drupal SQL dump used to preserve ordered per-video transcripts",
    )
    apply_hugo.add_argument(
        "--live-base-url",
        help="Current Drupal base URL used when the SQL snapshot lacks transcripts",
    )
    apply_hugo.add_argument(
        "--transcript-cache", type=Path,
        help="Local-only cache directory for live Drupal transcript JSON",
    )
    apply_hugo.add_argument("--confirm-apply", action="store_true")
    apply_hugo.set_defaults(function=command_apply_hugo)

    validate_hugo = commands.add_parser(
        "validate-hugo", help="Verify that the applied Hugo records match the plan"
    )
    validate_hugo.add_argument(
        "--hugo-plan", type=Path, default=DEFAULT_OUTPUT_DIR / "hugo-video-plan.csv"
    )
    validate_hugo.set_defaults(function=command_validate_hugo)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())
