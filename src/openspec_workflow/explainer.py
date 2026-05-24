from __future__ import annotations

import json
import os
import re
import shutil
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from openspec_workflow.manifest import build_manifest, write_manifest
from openspec_workflow.policy import ProjectPolicy, package_root
from openspec_workflow.validation import validate_explainer_artifact

PREFERRED_SKILL_IDS = (
    "deck-swiss-international",
    "ppt-keynote",
    "deck-open-slide-canvas",
    "deck-guizang-editorial",
)
PREFERRED_AGENT_IDS = ("pi",)
SYNC_FILES = ("proposal.md", "design.md", "tasks.md", "source-manifest.json")


class ExplainerGenerationError(RuntimeError):
    pass


class RequestFailure(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _read_optional(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "__intro__"
    sections[current] = []
    for line in text.splitlines():
        if line.startswith("#"):
            current = line.lstrip("#").strip().lower()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _first_nonempty_paragraph(text: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    if not blocks:
        return ""
    return re.sub(r"\s+", " ", blocks[0]).strip()


def _first_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[。！？.!?])\s+", text)
    return parts[0].strip() if parts else text


def _extract_bullets(text: str, *, limit: int = 3) -> list[str]:
    bullets: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^[-*]\s+", line):
            bullets.append(re.sub(r"^[-*]\s+", "", line).strip())
        elif re.match(r"^\d+\.\s+", line):
            bullets.append(re.sub(r"^\d+\.\s+", "", line).strip())
        if len(bullets) >= limit:
            break
    return bullets


def _pick_section(sections: dict[str, str], *candidates: str) -> str:
    for candidate in candidates:
        for key, value in sections.items():
            if candidate in key and value:
                return value
    return ""


def _truncate(text: str, *, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _list_items(values: list[str], *, fallback: list[str], count: int = 3) -> list[str]:
    data = [item for item in values if item]
    if not data:
        data = fallback
    if len(data) < count:
        data.extend(fallback[len(data) : count])
    return data[:count]


def _count_tasks(tasks_text: str) -> tuple[int, int, int]:
    done = len(re.findall(r"^- \[x\]", tasks_text, flags=re.MULTILINE | re.IGNORECASE))
    pending = len(re.findall(r"^- \[ \]", tasks_text, flags=re.MULTILINE))
    cancelled = len(re.findall(r"^- \[~\]", tasks_text, flags=re.MULTILINE))
    return done, pending, cancelled


def render_template_explainer(change_name: str, change_dir: Path, policy: ProjectPolicy) -> str:
    proposal_text = _read_optional(change_dir / "proposal.md")
    design_text = _read_optional(change_dir / "design.md")
    tasks_text = _read_optional(change_dir / "tasks.md")
    specs = sorted((change_dir / "specs").rglob("spec.md")) if (change_dir / "specs").exists() else []

    proposal_sections = _markdown_sections(proposal_text)
    design_sections = _markdown_sections(design_text)
    tasks_sections = _markdown_sections(tasks_text)

    why_text = _pick_section(proposal_sections, "why") or _pick_section(design_sections, "context")
    what_text = _pick_section(proposal_sections, "what changes") or _pick_section(proposal_sections, "scope")
    impact_text = _pick_section(proposal_sections, "impact") or _pick_section(design_sections, "risks")
    migration_text = _pick_section(design_sections, "migration") or _pick_section(design_sections, "rollout")
    status_text = _pick_section(tasks_sections, "validation") or _pick_section(tasks_sections, "implementation")
    in_scope_text = _pick_section(proposal_sections, "in")
    out_scope_text = _pick_section(proposal_sections, "out")

    summary = _first_sentence(what_text) or _first_sentence(why_text) or f"{change_name} change scaffold"
    why_paragraph = _first_nonempty_paragraph(why_text) or "這份 explainer 以現有 markdown/spec 來源檔為準，提供一個可離線閱讀的 companion view。"

    change_cards = _list_items(
        _extract_bullets(what_text, limit=3),
        fallback=[
            _first_sentence(what_text) or "彙整 proposal 內已明確陳述的變更內容。",
            _first_sentence(_pick_section(design_sections, "goals") or _pick_section(design_sections, "decisions"))
            or "彙整 design 內已明確陳述的設計方向。",
            _first_sentence(status_text) or "彙整 tasks 內已明確陳述的交付步驟。",
        ],
    )

    before_items = _list_items(
        _extract_bullets(why_text, limit=3),
        fallback=[
            _first_sentence(why_text) or "需要先讀 proposal/design/tasks 才能理解變更全貌。",
            "尚未假設任何超出 source files 的隱含需求。",
            "HTML explainer 只作為閱讀入口，不是新的 SSOT。",
        ],
    )
    after_items = _list_items(
        _extract_bullets(what_text + "\n" + impact_text, limit=3),
        fallback=[
            _first_sentence(what_text) or "把 source files 內已確認的內容整理成高理解度閱讀視圖。",
            _first_sentence(impact_text) or "保留對直接變更面與相關面之間的區分。",
            "仍以 markdown/spec artifacts 作為 authority layer。",
        ],
    )

    direct_surfaces = ["proposal.md", "design.md", "tasks.md"] + [spec.relative_to(change_dir).as_posix() for spec in specs[:3]]
    related_surfaces = [
        "source-manifest.json",
        ".openspec.yaml",
        "project policy overlay (.openspec-workflow.yaml)",
    ]
    direct_surfaces = _list_items(direct_surfaces, fallback=["proposal.md", "design.md", "tasks.md"])
    related_surfaces = _list_items(related_surfaces, fallback=["source-manifest.json", ".openspec.yaml", "project policy overlay"])

    in_scope_items = _list_items(
        _extract_bullets(in_scope_text, limit=3),
        fallback=[
            "僅描述 source files 已明示的變更內容。",
            "保留 explainer contract、source manifest、與 archive gate 的驗證邊界。",
            "允許 deterministic template fallback 與外部生成 backend 並存。",
        ],
    )
    out_scope_items = _list_items(
        _extract_bullets(out_scope_text, limit=3),
        fallback=[
            "不把 explainer 升格成新的規格來源。",
            "不替 source files 補寫未聲明的需求、承諾或 migration。",
            "不要求所有 harness 共用同一個 adapter 實作細節。",
        ],
    )

    rollout_steps = _list_items(
        _extract_bullets(migration_text, limit=3) + _extract_bullets(tasks_text, limit=3),
        fallback=[
            "先建立或更新 markdown/spec source files。",
            "重新產生 source-manifest.json 與 change-explainer.html。",
            "執行 explainer validation 與 archive preflight。",
        ],
    )

    done_count, pending_count, cancelled_count = _count_tasks(tasks_text)
    status_left_body = (
        f"目前 tasks 狀態：已完成 {done_count}、待處理 {pending_count}、取消 {cancelled_count}。"
        if tasks_text
        else "尚未提供 tasks.md，無法計算任務狀態。"
    )
    status_right_body = (
        f"目前偵測到 {len(specs)} 份 spec delta。"
        if specs
        else "目前尚未偵測到 spec delta；如果這個 change 需要 spec 變更，請補上 specs/ 內容。"
    )

    values = {
        "{{CHANGE_NAME}}": _escape_html(change_name),
        "{{ONE_SENTENCE_SUMMARY}}": _escape_html(summary),
        "{{KPI_PRIMARY_PROBLEM}}": _escape_html(_truncate(_first_sentence(why_paragraph), limit=48)),
        "{{KPI_SURFACES}}": str(3 + len(specs)),
        "{{KPI_SURFACES_NOTE}}": _escape_html("source files + spec deltas"),
        "{{KPI_PHASE}}": _escape_html("draft" if pending_count else "ready"),
        "{{KPI_PHASE_NOTE}}": _escape_html("derived from current tasks state"),
        "{{KPI_STATUS}}": _escape_html("planned" if pending_count else "validated"),
        "{{KPI_STATUS_NOTE}}": _escape_html("generated from tracked markdown artifacts"),
        "{{WHY_PARAGRAPH}}": _escape_html(_truncate(why_paragraph, limit=520)),
        "{{CHANGE_CARD_1_TITLE}}": "Proposal",
        "{{CHANGE_CARD_1_BODY}}": _escape_html(_truncate(change_cards[0], limit=220)),
        "{{CHANGE_CARD_2_TITLE}}": "Design",
        "{{CHANGE_CARD_2_BODY}}": _escape_html(_truncate(change_cards[1], limit=220)),
        "{{CHANGE_CARD_3_TITLE}}": "Tasks / Delivery",
        "{{CHANGE_CARD_3_BODY}}": _escape_html(_truncate(change_cards[2], limit=220)),
        "{{BEFORE_1_TITLE}}": "Current pressure",
        "{{BEFORE_1_BODY}}": _escape_html(_truncate(before_items[0], limit=220)),
        "{{BEFORE_2_TITLE}}": "Current constraint",
        "{{BEFORE_2_BODY}}": _escape_html(_truncate(before_items[1], limit=220)),
        "{{BEFORE_3_TITLE}}": "Current authority boundary",
        "{{BEFORE_3_BODY}}": _escape_html(_truncate(before_items[2], limit=220)),
        "{{AFTER_1_TITLE}}": "Planned change",
        "{{AFTER_1_BODY}}": _escape_html(_truncate(after_items[0], limit=220)),
        "{{AFTER_2_TITLE}}": "Planned impact",
        "{{AFTER_2_BODY}}": _escape_html(_truncate(after_items[1], limit=220)),
        "{{AFTER_3_TITLE}}": "Authority retained",
        "{{AFTER_3_BODY}}": _escape_html(_truncate(after_items[2], limit=220)),
        "{{FLOW_1_TITLE}}": "Source files",
        "{{FLOW_1_BODY}}": _escape_html("proposal.md / design.md / tasks.md / specs"),
        "{{FLOW_2_TITLE}}": "Manifest",
        "{{FLOW_2_BODY}}": _escape_html("source-manifest.json pins the explainer input set"),
        "{{FLOW_3_TITLE}}": "Explainer generation",
        "{{FLOW_3_BODY}}": _escape_html(f"backend={policy.change_explainer.backend}"),
        "{{FLOW_4_TITLE}}": "Validation + archive gate",
        "{{FLOW_4_BODY}}": _escape_html("presentation, manifest freshness, and task readiness checks"),
        "{{SURFACE_DIRECT_1}}": _escape_html(direct_surfaces[0]),
        "{{SURFACE_DIRECT_2}}": _escape_html(direct_surfaces[1]),
        "{{SURFACE_DIRECT_3}}": _escape_html(direct_surfaces[2]),
        "{{SURFACE_RELATED_1}}": _escape_html(related_surfaces[0]),
        "{{SURFACE_RELATED_2}}": _escape_html(related_surfaces[1]),
        "{{SURFACE_RELATED_3}}": _escape_html(related_surfaces[2]),
        "{{IN_SCOPE_1}}": _escape_html(_truncate(in_scope_items[0], limit=180)),
        "{{IN_SCOPE_2}}": _escape_html(_truncate(in_scope_items[1], limit=180)),
        "{{IN_SCOPE_3}}": _escape_html(_truncate(in_scope_items[2], limit=180)),
        "{{OUT_SCOPE_1}}": _escape_html(_truncate(out_scope_items[0], limit=180)),
        "{{OUT_SCOPE_2}}": _escape_html(_truncate(out_scope_items[1], limit=180)),
        "{{OUT_SCOPE_3}}": _escape_html(_truncate(out_scope_items[2], limit=180)),
        "{{ROLLOUT_1_TITLE}}": "Prepare sources",
        "{{ROLLOUT_1_BODY}}": _escape_html(_truncate(rollout_steps[0], limit=220)),
        "{{ROLLOUT_2_TITLE}}": "Generate artifacts",
        "{{ROLLOUT_2_BODY}}": _escape_html(_truncate(rollout_steps[1], limit=220)),
        "{{ROLLOUT_3_TITLE}}": "Validate before archive",
        "{{ROLLOUT_3_BODY}}": _escape_html(_truncate(rollout_steps[2], limit=220)),
        "{{STATUS_LEFT_TITLE}}": "Task progress",
        "{{STATUS_LEFT_BODY}}": _escape_html(status_left_body),
        "{{STATUS_RIGHT_TITLE}}": "Spec coverage",
        "{{STATUS_RIGHT_BODY}}": _escape_html(status_right_body),
    }

    template = (package_root() / "templates" / "change-explainer.template.html").read_text()
    for old, new in values.items():
        template = template.replace(old, new)
    return template


def json_request(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 30) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        raise RequestFailure(f"HTTP {err.code} for {method} {url}", status=err.code, body=body) from err
    except urllib.error.URLError as err:
        raise RequestFailure(f"Could not reach Open Design daemon at {url}: {err.reason}") from err
    return json.loads(text) if text.strip() else {}


def sse_chat(url: str, payload: dict[str, Any], *, timeout: int = 900) -> list[tuple[str | None, str]]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    events: list[tuple[str | None, str]] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            current_event: str | None = None
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("event:"):
                    current_event = line.partition(":")[2].strip() or None
                    continue
                if line.startswith("data:"):
                    data = line.partition(":")[2].lstrip()
                    events.append((current_event, data))
                    continue
                if line == "":
                    current_event = None
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        raise RequestFailure(f"HTTP {err.code} for POST {url}", status=err.code, body=body) from err
    except urllib.error.URLError as err:
        raise RequestFailure(f"Could not stream /api/chat from Open Design daemon at {url}: {err.reason}") from err
    return events


def choose_agent(daemon_url: str, override: str | None) -> str:
    agents_body = json_request(f"{daemon_url}/api/agents")
    agents = agents_body.get("agents") if isinstance(agents_body, dict) else None
    if not isinstance(agents, list):
        raise RequestFailure("Open Design /api/agents response did not contain an agents list")

    if override:
        for agent in agents:
            if isinstance(agent, dict) and agent.get("id") == override:
                return override
        raise RequestFailure(f"Requested Open Design agent id not found: {override}")

    usable: list[str] = []
    seen_ids: list[str] = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = agent.get("id")
        if not isinstance(agent_id, str) or not agent_id:
            continue
        seen_ids.append(agent_id)
        if any(agent.get(flag) is True for flag in ("installed", "available", "detected", "enabled")):
            usable.append(agent_id)
    for preferred in PREFERRED_AGENT_IDS:
        if preferred in usable:
            return preferred
    if usable:
        return usable[0]
    suffix = f" Seen ids: {', '.join(seen_ids)}." if seen_ids else ""
    raise RequestFailure("Open Design did not report any usable local agent." + suffix)


def choose_skill(daemon_url: str, override: str | None) -> str | None:
    try:
        skills_body = json_request(f"{daemon_url}/api/skills")
    except RequestFailure:
        return override
    skills = skills_body.get("skills") if isinstance(skills_body, dict) else None
    if not isinstance(skills, list):
        return override
    skill_ids = {
        skill.get("id")
        for skill in skills
        if isinstance(skill, dict) and isinstance(skill.get("id"), str)
    }
    if override:
        return override if override in skill_ids else None
    for preferred in PREFERRED_SKILL_IDS:
        if preferred in skill_ids:
            return preferred
    return None


def ensure_health(daemon_url: str) -> None:
    json_request(f"{daemon_url}/api/health")


def get_project(daemon_url: str, project_id: str) -> dict[str, Any] | None:
    try:
        body = json_request(f"{daemon_url}/api/projects/{urllib.parse.quote(project_id)}")
    except RequestFailure as err:
        if err.status == 404:
            return None
        raise
    return body if isinstance(body, dict) else None


def create_project(
    daemon_url: str,
    *,
    project_id: str,
    name: str,
    skill_id: str | None,
    custom_instructions: str,
) -> tuple[str, str]:
    payload: dict[str, Any] = {
        "id": project_id,
        "name": name,
        "customInstructions": custom_instructions,
        "skipDiscoveryBrief": True,
    }
    if skill_id:
        payload["skillId"] = skill_id
    body = json_request(f"{daemon_url}/api/projects", method="POST", payload=payload)
    if not isinstance(body, dict):
        raise RequestFailure("Unexpected response from Open Design project creation")
    conversation_id = body.get("conversationId")
    if not isinstance(conversation_id, str) or not conversation_id:
        raise RequestFailure("Open Design project creation did not return conversationId")
    return project_id, conversation_id


def patch_project(
    daemon_url: str,
    *,
    project_id: str,
    name: str,
    skill_id: str | None,
    custom_instructions: str,
) -> None:
    payload: dict[str, Any] = {"name": name, "customInstructions": custom_instructions, "skillId": skill_id}
    try:
        json_request(
            f"{daemon_url}/api/projects/{urllib.parse.quote(project_id)}",
            method="PATCH",
            payload=payload,
        )
    except RequestFailure:
        return


def create_conversation(daemon_url: str, project_id: str, title: str) -> str:
    body = json_request(
        f"{daemon_url}/api/projects/{urllib.parse.quote(project_id)}/conversations",
        method="POST",
        payload={"title": title},
    )
    if not isinstance(body, dict):
        raise RequestFailure("Unexpected response when creating Open Design conversation")
    conversation = body.get("conversation")
    if not isinstance(conversation, dict):
        raise RequestFailure("Open Design did not return a conversation object")
    conversation_id = conversation.get("id")
    if not isinstance(conversation_id, str) or not conversation_id:
        raise RequestFailure("Open Design conversation creation did not return id")
    return conversation_id


def sync_change_sources(change_dir: Path, resolved_dir: Path) -> None:
    resolved_dir.mkdir(parents=True, exist_ok=True)
    for rel in SYNC_FILES:
        src = change_dir / rel
        if not src.exists():
            continue
        dst = resolved_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    specs_src = change_dir / "specs"
    if specs_src.exists():
        shutil.copytree(specs_src, resolved_dir / "specs", dirs_exist_ok=True)
    artifact_path = resolved_dir / "change-explainer.html"
    if artifact_path.exists():
        artifact_path.unlink()


def read_prompt() -> str:
    return (package_root() / "prompts" / "opendesign-change-explainer.md").read_text()


def build_chat_message(change_name: str, locale: str) -> str:
    return textwrap.dedent(
        f"""
        output: change explainer html
        audience: reviewer, stakeholder, implementer
        locale: {locale}
        constraints: Do not ask questions. Use only local source files. Write a single self-contained change-explainer.html.

        Now generate or rewrite `change-explainer.html` for OpenSpec change `{change_name}`.

        Required workflow:
        1. Read `source-manifest.json` first.
        2. Read every source file listed in that manifest.
        3. Use those files as the only authoritative facts.
        4. Write `change-explainer.html` in the current project root.

        Hard output constraints:
        - single self-contained HTML file
        - no remote CSS, remote JS, remote fonts, or CDN assets
        - keep markdown/spec as SSOT
        - use Traditional Chinese (繁體中文) for reader-facing prose, headings, labels, and navigation chrome by default; keep only literal identifiers unchanged when needed
        - declare `<html lang=\"zh-Hant\">`
        - use a responsive document-style layout that stays readable on mobile, tablet, and desktop widths without horizontal overflow or clipped panels
        - do not use a fixed 1920×1080 stage, viewport-scaling slide shell, or hidden-overflow deck container as the primary reading experience
        - include section ids: why, what-changes, before-after, flow, affected-surfaces, scope-boundaries, rollout, current-status
        - do not create planning-brief.json or visual-script.json
        - do not ask follow-up questions
        """
    ).strip()


def generate_with_opendesign(change_name: str, change_dir: Path, policy: ProjectPolicy) -> str:
    manifest = build_manifest(change_name, change_dir)
    write_manifest(change_dir, manifest)

    daemon_url = os.environ.get(
        "OPENSPEC_OPEN_DESIGN_DAEMON_URL",
        policy.change_explainer.open_design.daemon_url,
    )
    agent_override = os.environ.get("OPENSPEC_OPEN_DESIGN_AGENT_ID", policy.change_explainer.open_design.agent_id)
    skill_override = os.environ.get("OPENSPEC_OPEN_DESIGN_SKILL_ID", policy.change_explainer.open_design.skill_id)
    project_id = f"{policy.change_explainer.open_design.project_prefix}-{change_name}"

    ensure_health(daemon_url)
    skill_id = choose_skill(daemon_url, skill_override)
    agent_id = choose_agent(daemon_url, agent_override)
    project_name = f"OpenSpec Change Explainer · {change_name}"
    prompt_text = read_prompt()
    project = get_project(daemon_url, project_id)
    if project is None:
        _, conversation_id = create_project(
            daemon_url,
            project_id=project_id,
            name=project_name,
            skill_id=skill_id,
            custom_instructions=prompt_text,
        )
        project = get_project(daemon_url, project_id)
        if project is None:
            raise RequestFailure("Open Design project was created but could not be reloaded")
    else:
        patch_project(
            daemon_url,
            project_id=project_id,
            name=project_name,
            skill_id=skill_id,
            custom_instructions=prompt_text,
        )
        conversation_id = create_conversation(
            daemon_url,
            project_id,
            f"Generate change explainer for {change_name}",
        )

    resolved_dir_raw = project.get("resolvedDir")
    if not isinstance(resolved_dir_raw, str) or not resolved_dir_raw:
        raise RequestFailure("Open Design project response did not include resolvedDir")
    resolved_dir = Path(resolved_dir_raw)
    sync_change_sources(change_dir, resolved_dir)

    payload: dict[str, Any] = {
        "agentId": agent_id,
        "projectId": project_id,
        "conversationId": conversation_id,
        "message": build_chat_message(change_name, policy.change_explainer.locale),
    }
    if skill_id:
        payload["skillId"] = skill_id
    sse_chat(f"{daemon_url}/api/chat", payload)

    generated_html = resolved_dir / "change-explainer.html"
    if not generated_html.exists():
        raise RequestFailure(
            "Open Design run completed without writing change-explainer.html. Use the template backend or inspect the Open Design project directory."
        )
    return generated_html.read_text()


def generate_explainer(change_name: str, change_dir: Path, policy: ProjectPolicy, backend: str | None = None) -> Path:
    selected_backend = backend or policy.change_explainer.backend
    if not change_dir.exists():
        raise ExplainerGenerationError(f"Change directory not found: {change_dir}")

    manifest = build_manifest(change_name, change_dir)
    write_manifest(change_dir, manifest)

    if selected_backend == "template":
        html = render_template_explainer(change_name, change_dir, policy)
    elif selected_backend == "opendesign":
        try:
            html = generate_with_opendesign(change_name, change_dir, policy)
        except RequestFailure as err:
            raise ExplainerGenerationError(str(err)) from err
    else:
        raise ExplainerGenerationError(f"Unsupported backend: {selected_backend}")

    output_path = change_dir / "change-explainer.html"
    output_path.write_text(html)

    validation = validate_explainer_artifact(change_name, change_dir, policy)
    if validation.status != "ok":
        raise ExplainerGenerationError(
            "Generated explainer did not pass validation: " + ", ".join(validation.data.get("errors", []))
        )
    return output_path
