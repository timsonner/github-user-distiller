#!/usr/bin/env python3
"""Create a distilled profile for a GitHub user's public codebase.

This script:
1. Fetches public repositories for a GitHub user.
2. Clones a small sample of them.
3. Extracts simple evidence like languages, manifests, and README text.
4. Uses the GitHub Copilot SDK when available to turn that evidence into a concise profile.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from copilot import CopilotClient
    from copilot.session import PermissionHandler
except Exception as exc:  # pragma: no cover - depends on local env
    CopilotClient = None
    PermissionHandler = None
    COPILOT_IMPORT_ERROR = exc
else:
    COPILOT_IMPORT_ERROR = None


def _http_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def fetch_user_repos(username: str, max_repos: int) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while len(repos) < max_repos:
        url = f"https://api.github.com/users/{username}/repos?per_page=100&page={page}"
        try:
            page_data = _http_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ValueError(f"User '{username}' was not found") from exc
            raise
        if not isinstance(page_data, list) or not page_data:
            break
        repos.extend(page_data)
        if len(page_data) < 100:
            break
        page += 1
    return repos[:max_repos]


def _is_text_file(path: Path) -> bool:
    if path.is_dir():
        return False
    if any(part in {".git", "node_modules", "__pycache__", ".venv"} for part in path.parts):
        return False
    return path.suffix.lower() in {
        ".py",
        ".md",
        ".txt",
        ".json",
        ".toml",
        ".yml",
        ".yaml",
        ".ini",
        ".cfg",
        ".sh",
        ".ps1",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".php",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        "",
    }


def gather_repo_signals(repo_dir: Path) -> dict[str, Any]:
    files = [p for p in repo_dir.rglob("*") if _is_text_file(p)]
    file_types = Counter(path.suffix.lower() for path in files if path.suffix.lower())

    readme_candidates = [p for p in files if p.name.lower().startswith("readme")]
    readme_excerpt = ""
    if readme_candidates:
        readme_path = sorted(readme_candidates, key=lambda p: len(p.parts))[0]
        try:
            readme_excerpt = readme_path.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError:
            readme_excerpt = ""

    manifest_names = ["pyproject.toml", "requirements.txt", "package.json", "setup.py", "Cargo.toml", "go.mod", "Pipfile"]
    manifest_summary = ""
    for manifest_name in manifest_names:
        manifest_path = repo_dir / manifest_name
        if manifest_path.exists():
            try:
                manifest_summary = manifest_path.read_text(encoding="utf-8", errors="ignore")[:800]
                break
            except OSError:
                pass

    language_counter: Counter[str] = Counter()
    for path in files:
        suffix = path.suffix.lower()
        if suffix == ".py":
            language_counter["python"] += 1
        elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
            language_counter["javascript/typescript"] += 1
        elif suffix == ".go":
            language_counter["go"] += 1
        elif suffix == ".rs":
            language_counter["rust"] += 1
        elif suffix == ".java":
            language_counter["java"] += 1
        elif suffix == ".rb":
            language_counter["ruby"] += 1
        elif suffix in {".c", ".cpp", ".h", ".hpp"}:
            language_counter["c/c++"] += 1

    return {
        "file_types": dict(file_types),
        "languages": dict(language_counter),
        "manifest_summary": manifest_summary,
        "readme_excerpt": readme_excerpt,
    }


def heuristic_profile(repo_signals: list[dict[str, Any]], username: str) -> str:
    language_counter: Counter[str] = Counter()
    for signal in repo_signals:
        language_counter.update(signal["languages"])

    lines = [f"GitHub user: {username}", "Observed patterns:"]
    if language_counter:
        lines.append(f"- Preferred languages: {', '.join(sorted(language_counter.keys()))}")
    if any("python" in signal["languages"] for signal in repo_signals):
        lines.append("- The user appears to build Python-heavy tooling and services.")
    if any("javascript/typescript" in signal["languages"] for signal in repo_signals):
        lines.append("- The user also appears to work on web or frontend-oriented code.")
    if any(signal["manifest_summary"] for signal in repo_signals):
        lines.append("- The repositories include packaged projects or dependency manifests.")
    return "\n".join(lines)


async def build_profile_with_copilot(repo_signals: list[dict[str, Any]], username: str, model: str | None = None) -> str:
    if CopilotClient is None or PermissionHandler is None:
        return heuristic_profile(repo_signals, username)

    summaries = []
    for signal in repo_signals:
        summary_parts = [f"repo: {signal.get('repo_name', 'unknown')}"]
        if signal.get("description"):
            summary_parts.append(f"description: {signal.get('description')}")
        if signal.get("languages"):
            summary_parts.append(f"languages: {', '.join(signal['languages'].keys())}")
        if signal.get("manifest_summary"):
            summary_parts.append(f"manifest: {signal['manifest_summary'][:300]}")
        if signal.get("readme_excerpt"):
            summary_parts.append(f"readme: {signal['readme_excerpt'][:400]}")
        summaries.append(" | ".join(summary_parts))

    requested_model = model or os.getenv("COPILOT_MODEL") or os.getenv("GITHUB_COPILOT_MODEL")
    session_kwargs = {
        "on_permission_request": PermissionHandler.approve_all,
        "system_message": {
            "mode": "append",
            "content": (
                "You are a codebase distiller. Read the repository summaries and produce a concise profile of "
                "the user's coding style, likely interests, and project intentions."
            ),
        },
    }
    if requested_model:
        session_kwargs["model"] = requested_model

    try:
        client = CopilotClient()
        await client.start()
        try:
            session = await client.create_session(**session_kwargs)
        except Exception as exc:
            if requested_model and "not available" in str(exc).lower():
                print(f"Requested model '{requested_model}' is unavailable; retrying without an explicit model.", file=sys.stderr)
                session_kwargs.pop("model", None)
                session = await client.create_session(**session_kwargs)
            else:
                raise
        prompt = (
            "Create a concise profile of this GitHub user's codebase. "
            "Focus on recurring themes, preferred languages, likely intentions, and style.\n\n"
            + "\n".join(summaries)
        )
        response = await session.send_and_wait(prompt)
        await client.stop()
        if getattr(response, "data", None) and getattr(response.data, "content", None):
            return response.data.content
    except Exception as exc:
        print(f"Copilot SDK path failed: {exc}", file=sys.stderr)
        print("Falling back to heuristic profile because Copilot authentication is unavailable.", file=sys.stderr)

    return heuristic_profile(repo_signals, username)


async def distill_user(username: str, max_repos: int, output_path: str | None, model: str | None = None) -> dict[str, Any]:
    repos = fetch_user_repos(username, max_repos)
    if not repos:
        raise ValueError(f"No repositories found for '{username}'")

    repo_signals: list[dict[str, Any]] = []
    temp_root = Path(tempfile.mkdtemp(prefix="github-user-distill-", dir="."))
    try:
        for repo in repos:
            repo_name = repo.get("name")
            if not repo_name:
                continue
            repo_dir = temp_root / repo_name
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", repo.get("html_url", ""), str(repo_dir)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                print(f"Skipping {repo_name}: {exc}", file=sys.stderr)
                continue

            signal = gather_repo_signals(repo_dir)
            signal["repo_name"] = repo_name
            signal["description"] = repo.get("description", "") or ""
            signal["html_url"] = repo.get("html_url", "")
            repo_signals.append(signal)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    profile_text = await build_profile_with_copilot(repo_signals, username, model=model)

    payload = {
        "user": username,
        "repo_count": len(repo_signals),
        "repos": [
            {
                "repo_name": signal.get("repo_name"),
                "description": signal.get("description"),
                "languages": signal.get("languages", {}),
                "file_types": signal.get("file_types", {}),
                "manifest_summary": signal.get("manifest_summary", "")[:400],
            }
            for signal in repo_signals
        ],
        "profile": profile_text,
    }

    if output_path:
        Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Distill a GitHub user's public codebase")
    parser.add_argument("username", help="GitHub username to analyze")
    parser.add_argument("--max-repos", type=int, default=5, help="Maximum number of repos to inspect")
    parser.add_argument("--output", help="Optional path to write JSON output")
    parser.add_argument("--model", help="Optional Copilot model override; if omitted the SDK/runtime default is used")
    args = parser.parse_args()

    if COPILOT_IMPORT_ERROR is not None:
        print(f"Copilot SDK import warning: {COPILOT_IMPORT_ERROR}", file=sys.stderr)

    model = args.model or os.getenv("COPILOT_MODEL") or os.getenv("GITHUB_COPILOT_MODEL")
    payload = asyncio.run(distill_user(args.username, args.max_repos, args.output, model=model))
    print(payload["profile"])
    if COPILOT_IMPORT_ERROR is not None:
        print("Note: Copilot SDK authentication is not available, so the script used a heuristic profile fallback.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
