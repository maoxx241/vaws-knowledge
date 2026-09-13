"""Bounded source snapshots; never execute repository code or follow source links."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterator

from .common import Budget, ImportLimit, IntakeError, Item, bounded_read, command, digest, inside

SUPPORTED = {".md", ".markdown", ".txt", ".html", ".htm", ".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PR_REPOSITORIES = {"vllm-project/vllm", "vllm-project/vllm-ascend"}


def normalize(spec: str | dict) -> dict:
    value = {"url": spec} if isinstance(spec, str) and spec.startswith(("http://", "https://")) else {"path": spec} if isinstance(spec, str) else dict(spec)
    if not value.get("type"):
        value["type"] = "github_pr" if re.match(r"https://github\.com/[^/]+/[^/]+/pull/\d+/?$", value.get("url", "")) else "url" if "url" in value else "local"
    if value["type"] not in {"local", "url", "git", "github_pr"}:
        raise ValueError("source type must be local, url, git or github_pr")
    if value.get("path"):
        value["path"] = str(Path(value["path"]).absolute())
    return value


def source_identity(spec: dict) -> str:
    # Changing a conversion option updates the existing material instead of creating duplicates.
    identity = {k: spec[k] for k in ("type", "path", "url", "repo", "number", "ref", "paths") if k in spec}
    return digest(identity)[:24]


def selected(name: str, patterns: list[str] | None) -> bool:
    if Path(name).suffix.lower() not in SUPPORTED:
        return False
    return not patterns or any(fnmatch.fnmatch(name, pattern) or name == pattern or name.startswith(pattern.rstrip("/") + "/") for pattern in patterns)


def _selected_subtree(prefix: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    for pattern in patterns:
        literal = re.split(r"[?*\[]", pattern, 1)[0]
        if not literal or literal.startswith(prefix) or prefix.startswith(literal.rstrip("/") + "/"):
            return True
    return False


def _url_bytes(url: str, budget: Budget, *, max_bytes: int | None = None) -> tuple[bytes, dict]:
    """DNS, redirects and slow socket reads share one hard process deadline."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("source URL must be HTTP(S), without embedded credentials")
    limit = min(max_bytes or budget.limits.file_bytes, budget.limits.total_bytes - budget.bytes)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
    _, raw = command([sys.executable, "-m", "knowledge_intake.fetch", url, str(limit), str(budget.remaining()), str(budget.limits.memory_mb)], timeout=budget.remaining(), max_bytes=limit + 16_384, env=env)
    header, separator, data = raw.partition(b"\n")
    if not separator or len(data) > limit:
        raise ImportLimit("download byte budget reached")
    details = json.loads(header)
    if details.get("error"):
        raise IntakeError(details["error"])
    return data, details


def _url_bytes_in_process(url: str, budget: Budget, *, max_bytes: int | None = None) -> tuple[bytes, dict]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("source URL must be HTTP(S), without embedded credentials")
    limit = min(max_bytes or budget.limits.file_bytes, budget.limits.total_bytes - budget.bytes)
    request = urllib.request.Request(url, headers={"User-Agent": "knowledge-intake/0.1", "Accept": "application/json, text/html, */*"})
    try:
        with urllib.request.urlopen(request, timeout=budget.remaining()) as response:
            if urllib.parse.urlsplit(response.url).scheme not in {"http", "https"}:
                raise ValueError("unsupported redirect protocol")
            chunks, count = [], 0
            while True:
                budget.check()
                # read1 returns available transport data, letting the absolute
                # budget run even when a server trickles a never-ending body.
                block = response.read1(min(64 * 1024, limit + 1 - count))
                if not block:
                    break
                chunks.append(block)
                count += len(block)
                if count > limit:
                    raise ImportLimit("download byte budget reached")
            return b"".join(chunks), {"url": response.url, "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified"), "content_type": response.headers.get("Content-Type", "")}
    except urllib.error.HTTPError as exc:
        raise IntakeError(f"source HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise IntakeError(f"source network failed: {type(exc.reason).__name__}") from exc


def _gh_path() -> str | None:
    executable = shutil.which("gh")
    if not executable and os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "GitHub CLI/gh.exe"
        if candidate.is_file():
            executable = str(candidate)
    return executable


def github_api(endpoint: str, budget: Budget) -> object:
    executable = _gh_path()
    budget.scan()
    if executable:
        _, raw = command([executable, "api", endpoint], timeout=budget.remaining(), max_bytes=min(budget.limits.file_bytes, budget.limits.total_bytes - budget.bytes))
    else:
        raw, _ = _url_bytes("https://api.github.com/" + endpoint, budget)
    # Count actual network bytes separately from documents; API pagination consumes the same total limit.
    budget.bytes += len(raw)
    if budget.bytes > budget.limits.total_bytes:
        raise ImportLimit("source byte budget reached")
    return json.loads(raw)


def _pages(endpoint: str, budget: Budget, scan: dict, max_items: int) -> list:
    results = []
    page = 1
    while True:
        rows = github_api(f"{endpoint}{'&' if '?' in endpoint else '?'}per_page=100&page={page}", budget)
        if not isinstance(rows, list):
            raise IntakeError("unexpected GitHub collection")
        remaining = max_items - len(results)
        results.extend(rows[:remaining])
        if len(rows) > remaining or len(results) >= max_items and len(rows) == 100:
            scan["warnings"].append(f"GitHub collection bounded at {max_items} items: {endpoint}")
            scan["complete"] = False
            return results
        if len(rows) < 100:
            return results
        page += 1


def _local(spec: dict, budget: Budget, excluded: list[Path]) -> Iterator[Item]:
    root = Path(spec["path"])
    if root.is_symlink():
        raise ValueError("source root must not be a symlink")
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        budget.scan()
        if root.suffix.lower() not in SUPPORTED:
            raise ValueError(f"unsupported source format: {root.suffix}")
        data = bounded_read(root, budget)
        yield Item(root.name, root.name, data, str(root.resolve()), digest(data))
        return
    def visit(directory: Path) -> Iterator[Path]:
        with os.scandir(directory) as entries:
            for entry in entries:
                budget.scan()
                path = Path(entry.path)
                if entry.is_symlink() or not inside(path, root) or any(inside(path, base) for base in excluded):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in {".git", ".venv", "__pycache__", "node_modules"}:
                        yield from visit(path)
                elif entry.is_file(follow_symlinks=False):
                    yield path
    for path in visit(root):
        relative = path.relative_to(root).as_posix()
        if selected(relative, spec.get("paths")):
            data = bounded_read(path, budget)
            yield Item(relative, path.name, data, str(path.resolve()), digest(data), {"relative_path": relative})


def _github_pr(spec: dict, budget: Budget, scan: dict) -> Iterator[Item]:
    match = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)/?$", spec.get("url", ""))
    repo = match[1] if match else str(spec.get("repo", ""))
    number = int(match[2] if match else spec.get("number", 0))
    if repo not in PR_REPOSITORIES or number <= 0:
        raise ValueError("PR experience intake supports vllm-project/vllm and vllm-project/vllm-ascend only")
    prefix = f"repos/{repo}"
    pr = github_api(f"{prefix}/pulls/{number}", budget)
    revision = {"base": pr["base"]["sha"], "head": pr["head"]["sha"], "updated_at": pr["updated_at"], "merge_commit": pr.get("merge_commit_sha")}
    limit = min(int(spec.get("max_pr_items", 300)), budget.limits.scan_entries)
    if limit <= 0:
        raise ValueError("max_pr_items must be positive")
    files = _pages(f"{prefix}/pulls/{number}/files", budget, scan, limit)
    comments = _pages(f"{prefix}/issues/{number}/comments", budget, scan, limit)
    reviews = _pages(f"{prefix}/pulls/{number}/comments", budget, scan, limit)
    if len(files) < pr.get("changed_files", len(files)):
        scan["complete"] = False
        scan["warnings"].append("PR file list is incomplete")
    url = f"https://github.com/{repo}/pull/{number}"
    lines = [f"# {pr['title']}", "", f"Source: {url}", f"State: {pr['state']}; merged: {bool(pr.get('merged'))}",
             f"Base revision: `{revision['base']}`", f"Head revision: `{revision['head']}`", "", "## PR description", "", pr.get("body") or "(No description)", "", "## Changed files", ""]
    for item in files:
        lines += [f"### {item['filename']}", "", f"Status: {item['status']}; +{item['additions']} / -{item['deletions']}", ""]
        if item.get("patch"):
            # The API can omit or truncate diffs. Explicitly call this an API patch excerpt.
            lines += ["API patch excerpt (the pinned file is the complete-source reference):", "", "````diff", item["patch"], "````", ""]
        else:
            scan["warnings"].append(f"No API patch supplied: {item['filename']}")
        quoted = urllib.parse.quote(item["filename"], safe="/")
        if item["status"] != "removed":
            lines.append(f"Pinned head: https://github.com/{repo}/blob/{revision['head']}/{quoted}")
        if item["status"] != "added":
            base_name = urllib.parse.quote(item.get("previous_filename", item["filename"]), safe="/")
            lines.append(f"Pinned base: https://github.com/{repo}/blob/{revision['base']}/{base_name}")
        lines.append("")
    lines += ["## Discussion and review", ""]
    for item in comments + reviews:
        lines += [f"### {item.get('html_url', url)}", "", f"Updated: {item.get('updated_at')}; author: {(item.get('user') or {}).get('login', 'unknown')}", "", item.get("body") or "(Empty)", ""]
    lines += ["## Scope of this snapshot", "", "This records PR claims, discussion and API patch excerpts. It is not execution evidence. Large or binary diffs may be omitted by GitHub; use the pinned source links above."]
    data = "\n".join(lines).encode("utf-8")
    budget.take(len(data))
    scan["revision"] = revision
    yield Item(f"{repo}#{number}", f"{repo.split('/')[-1]}-pr-{number}.md", data, url, revision,
               {"kind": "github_pr", "patches": "api_excerpts", "complete_file_count": pr.get("changed_files"), "observed_file_count": len(files), "warnings": list(scan["warnings"]), "partial": not scan["complete"]})


def _git(spec: dict, budget: Budget, scan: dict) -> Iterator[Item]:
    ref = str(spec.get("ref", "HEAD"))
    if ref.startswith("-"):
        raise ValueError("invalid git ref")
    if spec.get("path"):
        root = Path(spec["path"])
        _, raw = command(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=root, timeout=budget.remaining(), max_bytes=4096)
        revision = raw.decode("ascii").strip()
        _, raw = command(["git", "ls-tree", "-r", "-z", revision], cwd=root, timeout=budget.remaining(), max_bytes=budget.limits.file_bytes)
        scan["revision"] = revision
        for entry in raw.split(b"\0"):
            if not entry:
                continue
            budget.scan()
            header, name = entry.split(b"\t", 1)
            mode, kind, blob = header.split()
            relative = name.decode("utf-8")
            if mode not in {b"100644", b"100755"} or kind != b"blob" or not selected(relative, spec.get("paths")):
                continue
            _, data = command(["git", "cat-file", "blob", blob.decode("ascii")], cwd=root, timeout=budget.remaining(), max_bytes=min(budget.limits.file_bytes, budget.limits.total_bytes - budget.bytes))
            budget.take(len(data))
            yield Item(relative, Path(relative).name, data, f"{root.resolve()}@{revision}:{relative}", revision, {"relative_path": relative, "git_blob": blob.decode()})
        return
    match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?", spec.get("url", ""))
    if not match:
        raise ValueError("remote git intake accepts a GitHub repository URL; other Git servers can use a local clone")
    repo = match[1]
    commit = github_api(f"repos/{repo}/commits/{urllib.parse.quote(ref, safe='')}", budget)
    revision = commit["sha"]
    scan["revision"] = revision
    todo = [("", commit["commit"]["tree"]["sha"])]
    while todo:
        prefix, tree_sha = todo.pop()
        tree = github_api(f"repos/{repo}/git/trees/{tree_sha}", budget)
        if tree.get("truncated"):
            scan["complete"] = False
            scan["warnings"].append(f"GitHub tree truncated: {prefix or '/'}")
        for entry in tree["tree"]:
            budget.scan()
            name = prefix + entry["path"]
            if entry["type"] == "tree" and _selected_subtree(name + "/", spec.get("paths")):
                todo.append((name + "/", entry["sha"]))
            elif entry["type"] == "blob" and entry["mode"] in {"100644", "100755"} and selected(name, spec.get("paths")):
                if entry.get("size", 0) > budget.limits.file_bytes:
                    raise ImportLimit("git blob byte budget reached")
                raw_url = f"https://raw.githubusercontent.com/{repo}/{revision}/{urllib.parse.quote(name, safe='/')}"
                data, _ = _url_bytes(raw_url, budget)
                budget.take(len(data))
                yield Item(name, Path(name).name, data, f"https://github.com/{repo}/blob/{revision}/{urllib.parse.quote(name, safe='/')}", revision, {"relative_path": name, "git_blob": entry["sha"]})


def iter_source(spec: dict, budget: Budget, scan: dict, excluded: list[Path]) -> Iterator[Item]:
    if spec["type"] == "local":
        yield from _local(spec, budget, excluded)
    elif spec["type"] == "github_pr":
        yield from _github_pr(spec, budget, scan)
    elif spec["type"] == "git":
        yield from _git(spec, budget, scan)
    else:
        data, details = _url_bytes(spec["url"], budget)
        budget.take(len(data))
        name = str(spec.get("filename") or Path(urllib.parse.urlsplit(spec["url"]).path).name or "document")
        if Path(name).suffix.lower() not in SUPPORTED:
            content_type = details["content_type"]
            suffix = ".html" if "html" in content_type else ".pdf" if "pdf" in content_type else ".txt" if "text/" in content_type else None
            if suffix is None:
                raise ValueError("URL needs a supported filename or recognized Content-Type")
            name += suffix
        revision = {"etag": details["etag"], "last_modified": details["last_modified"], "sha256": digest(data)}
        scan["revision"] = revision
        yield Item(spec["url"], name, data, spec["url"], revision, details)
