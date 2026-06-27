#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass


UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
TEAMWORK_ROLE = "Teamwork Multi-Agent Team"


def normalize_repo_locator(value: str) -> str:
    value = value.strip().lower()
    for prefix in ("https://", "http://", "ssh://", "git@"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    value = value.replace(":", "/", 1)
    value = value.removesuffix(".git").rstrip("/")
    return value


def repo_locator_tail(value: str) -> str:
    parts = [part for part in value.split("/") if part]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return ""


def emit_repo_locator_variants(value: str) -> set[str]:
    normalized = normalize_repo_locator(value)
    if not normalized:
        return set()
    variants = {normalized}
    tail = repo_locator_tail(normalized)
    if tail:
        variants.add(tail)
    return variants


def shell_output(*args: str) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def project_repo_locator_candidates(workspace_root: str) -> set[str]:
    candidates: set[str] = set()
    for remote_name in ("origin", "upstream"):
        remote_url = shell_output(
            "git",
            "-C",
            workspace_root,
            "config",
            "--get",
            f"remote.{remote_name}.url",
        )
        if not remote_url:
            continue
        candidates.update(emit_repo_locator_variants(remote_url))
    return candidates


def conversation_file_mtimes(conversation_dir: str) -> dict[str, float]:
    mtimes: dict[str, float] = {}
    if not os.path.isdir(conversation_dir):
        return mtimes

    for entry in os.scandir(conversation_dir):
        if not entry.is_file():
            continue
        match = UUID_RE.match(entry.name.split(".", 1)[0])
        if not match or not entry.name.endswith((".pb", ".db")):
            continue
        conversation_id = match.group(0)
        try:
            mtimes[conversation_id] = max(mtimes.get(conversation_id, 0), entry.stat().st_mtime)
        except OSError:
            continue
    return mtimes


@dataclass
class ConversationNode:
    conversation_id: str
    parent_id: str
    role: str
    is_root: bool
    matches_project: bool
    mtime: float

    @property
    def is_teamwork(self) -> bool:
        return TEAMWORK_ROLE in self.role


class Resolver:
    def __init__(self, workspace_root: str, conversation_dir: str, ag_path: str, limit: int) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.project_uri = f"file://{self.workspace_root.replace(' ', '%20')}"
        self.conversation_dir = conversation_dir
        self.ag_path = ag_path
        self.limit = limit
        self.repo_candidates = project_repo_locator_candidates(self.workspace_root)
        self.file_mtimes = conversation_file_mtimes(conversation_dir)
        self.node_cache: dict[str, ConversationNode | None] = {}

    def last_conversation_id(self) -> str:
        last_id = shell_output(self.ag_path, "last")
        return last_id if UUID_RE.match(last_id) else ""

    def recent_ids(self) -> list[str]:
        ordered = sorted(self.file_mtimes.items(), key=lambda item: item[1], reverse=True)
        return [conversation_id for conversation_id, _ in ordered[: self.limit]]

    def fetch_metadata(self, conversation_id: str) -> dict | None:
        raw = shell_output(self.ag_path, "meta", conversation_id)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return (
            data.get("response", {})
            .get("conversationMetadata", {})
            .get("metadata", {})
        ) or None

    def metadata_matches_project(self, metadata: dict) -> bool:
        workspace_uris = metadata.get("workspaceUris") or []
        if any(str(uri).startswith(self.project_uri) for uri in workspace_uris):
            return True

        for workspace in metadata.get("workspaces") or []:
            workspace_folder = str(workspace.get("workspaceFolderAbsoluteUri") or "")
            git_root = str(workspace.get("gitRootAbsoluteUri") or "")
            if workspace_folder.startswith(self.project_uri) or git_root.startswith(self.project_uri):
                return True

            repository = workspace.get("repository") or {}
            for field in ("gitOriginUrl", "gitUpstreamUrl", "computedName", "reportedName", "modelName"):
                for candidate in emit_repo_locator_variants(str(repository.get(field) or "")):
                    if candidate in self.repo_candidates:
                        return True

        repository = metadata.get("repository") or {}
        for field in ("gitOriginUrl", "gitUpstreamUrl", "computedName", "reportedName", "modelName"):
            for candidate in emit_repo_locator_variants(str(repository.get(field) or "")):
                if candidate in self.repo_candidates:
                    return True

        return False

    def node(self, conversation_id: str) -> ConversationNode | None:
        if not conversation_id:
            return None
        if conversation_id in self.node_cache:
            return self.node_cache[conversation_id]

        metadata = self.fetch_metadata(conversation_id)
        if metadata is None:
            self.node_cache[conversation_id] = None
            return None

        subagent_spec = metadata.get("subagentSpec")
        node = ConversationNode(
            conversation_id=conversation_id,
            parent_id=str(metadata.get("parentConversationId") or ""),
            role=str((subagent_spec or {}).get("role") or ""),
            is_root=subagent_spec is None,
            matches_project=self.metadata_matches_project(metadata),
            mtime=self.file_mtimes.get(conversation_id, 0),
        )
        self.node_cache[conversation_id] = node
        return node

    def ancestor_chain(self, conversation_id: str) -> list[ConversationNode]:
        chain: list[ConversationNode] = []
        current_id = conversation_id
        seen: set[str] = set()

        while current_id and current_id not in seen:
            seen.add(current_id)
            node = self.node(current_id)
            if node is None:
                break
            chain.append(node)
            current_id = node.parent_id

        return chain

    def nearest_teamwork_ancestor(self, conversation_id: str) -> str:
        for node in self.ancestor_chain(conversation_id):
            if node.is_teamwork and node.matches_project:
                return node.conversation_id
        return ""

    def root_ancestor(self, conversation_id: str) -> str:
        chain = self.ancestor_chain(conversation_id)
        for node in reversed(chain):
            if node.is_root and node.matches_project:
                return node.conversation_id
        return ""

    def latest_teamwork_candidate(self, canonical_root_id: str = "") -> str:
        for conversation_id in self.recent_ids():
            node = self.node(conversation_id)
            if node is None or not node.matches_project or not node.is_teamwork:
                continue
            if canonical_root_id and self.root_ancestor(conversation_id) != canonical_root_id:
                continue
            return conversation_id
        return ""

    def latest_root_candidate(self) -> str:
        for conversation_id in self.recent_ids():
            node = self.node(conversation_id)
            if node is None or not node.matches_project or not node.is_root:
                continue
            return conversation_id
        return ""

    def resolve(self) -> dict[str, str]:
        active_project_id = ""
        canonical_id = ""
        teamwork_id = ""
        reason = "unresolved"

        original_active_id = self.last_conversation_id()

        # Find the most recently modified conversation that matches this project
        most_recent_project_id = ""
        for conversation_id in self.recent_ids():
            node = self.node(conversation_id)
            if node is not None and node.matches_project:
                most_recent_project_id = conversation_id
                break

        # If we have a matching recent conversation, and it is newer than the cached active id
        # (or the cached active id is empty or doesn't match project), use the most recent one.
        resolved_active_id = original_active_id
        if most_recent_project_id:
            active_node = self.node(resolved_active_id) if resolved_active_id else None
            if not resolved_active_id or (active_node is not None and not active_node.matches_project):
                resolved_active_id = most_recent_project_id
            else:
                cached_mtime = self.file_mtimes.get(resolved_active_id, 0)
                recent_mtime = self.file_mtimes.get(most_recent_project_id, 0)
                if recent_mtime > cached_mtime:
                    resolved_active_id = most_recent_project_id

        active_node = self.node(resolved_active_id) if resolved_active_id else None
        if active_node is not None and active_node.matches_project:
            active_project_id = resolved_active_id
            canonical_id = self.root_ancestor(resolved_active_id)
            teamwork_id = self.nearest_teamwork_ancestor(resolved_active_id)
            if teamwork_id:
                reason = "active_chain"
            elif canonical_id:
                reason = "active_root"

        if not canonical_id and teamwork_id:
            canonical_id = self.root_ancestor(teamwork_id)
            if canonical_id:
                reason = "teamwork_parent"

        if not teamwork_id:
            teamwork_id = self.latest_teamwork_candidate(canonical_root_id=canonical_id)
            if teamwork_id and not canonical_id:
                canonical_id = self.root_ancestor(teamwork_id)
            if teamwork_id and reason == "unresolved":
                reason = "recent_teamwork"

        if not canonical_id:
            canonical_id = self.latest_root_candidate()
            if canonical_id and reason == "unresolved":
                reason = "recent_root"

        if canonical_id and not teamwork_id:
            teamwork_id = self.latest_teamwork_candidate(canonical_root_id=canonical_id)
            if teamwork_id and reason in {"unresolved", "recent_root"}:
                reason = "canonical_teamwork"

        # Restore the resolved active conversation ID to prevent metadata queries
        # from corrupting the user's last conversation state.
        if resolved_active_id:
            try:
                cache_dir = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "antigravity-send")
                last_file = os.path.join(cache_dir, "last_conversation_id")
                os.makedirs(cache_dir, exist_ok=True)
                with open(last_file, "w", encoding="utf-8") as f:
                    f.write(resolved_active_id + "\n")
            except Exception:
                pass

        return {
            "active_conversation_id": active_project_id,
            "canonical_conversation_id": canonical_id,
            "jammini_team_conversation_id": teamwork_id,
            "resolution_reason": reason,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--conversation-dir", required=True)
    parser.add_argument("--ag-path", required=True)
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    resolver = Resolver(
        workspace_root=args.workspace_root,
        conversation_dir=args.conversation_dir,
        ag_path=args.ag_path,
        limit=args.limit,
    )
    resolved = resolver.resolve()
    for key, value in resolved.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
