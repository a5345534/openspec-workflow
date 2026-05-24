from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openspec_workflow.manifest import freshness_report, load_json, validator_errors
from openspec_workflow.policy import ProjectPolicy, package_root

VIEWPORT_CASES = (
    ("mobile", 390, 844),
    ("tablet", 768, 1024),
    ("desktop", 1280, 800),
)

REMOTE_DEP_RE = re.compile(
    r'<(?:script|link|img|iframe|video|audio)[^>]+(?:src|href)=["\']https?://|@import\s+url\(["\']?https?://|url\(["\']?https?://',
    flags=re.IGNORECASE,
)


@dataclass(slots=True)
class ValidationResult:
    status: str
    data: dict[str, Any]


@dataclass(slots=True)
class TaskCheckResult:
    blocking: list[str]
    backlog: list[str]


def strip_tags(text: str) -> str:
    text = re.sub(r"<script\b[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style\b[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--([\s\S]*?)-->", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def find_browser() -> str | None:
    for name in ("google-chrome", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def build_probe_html(target_html: str) -> str:
    source = json.dumps(target_html)
    cases = json.dumps(
        [{"name": name, "width": width, "height": height} for name, width, height in VIEWPORT_CASES]
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\">
  <title>openspec-workflow-layout-probe</title>
</head>
<body>
  <pre id=\"result\">pending</pre>
  <script>
    const source = {source};
    const cases = {cases};
    async function wait(ms) {{ return new Promise((resolve) => setTimeout(resolve, ms)); }}
    async function runCase(spec) {{
      const host = document.createElement('div');
      host.style.width = spec.width + 'px';
      host.style.height = spec.height + 'px';
      host.style.position = 'absolute';
      host.style.left = '0';
      host.style.top = '0';
      host.style.overflow = 'hidden';
      const frame = document.createElement('iframe');
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
      frame.style.width = '100%';
      frame.style.height = '100%';
      frame.style.border = '0';
      host.appendChild(frame);
      document.body.appendChild(host);
      await new Promise((resolve) => {{
        let finished = false;
        const done = () => {{
          if (finished) return;
          finished = true;
          setTimeout(resolve, 350);
        }};
        frame.onload = done;
        setTimeout(done, 3500);
        frame.srcdoc = source;
      }});
      const doc = frame.contentDocument;
      const root = doc && doc.documentElement ? doc.documentElement : null;
      const body = doc && doc.body ? doc.body : root;
      const scrollWidth = Math.max(root ? root.scrollWidth : 0, body ? body.scrollWidth : 0);
      const clientWidth = frame.clientWidth;
      const offscreen = [];
      if (doc && body) {{
        const walker = doc.createTreeWalker(body, NodeFilter.SHOW_ELEMENT);
        while (walker.nextNode()) {{
          const el = walker.currentNode;
          const rect = el.getBoundingClientRect();
          if (!rect || rect.width <= 0 || rect.height <= 0) continue;
          if (rect.left < clientWidth && rect.right > clientWidth + 4) {{
            offscreen.push(el.tagName.toLowerCase());
            if (offscreen.length >= 8) break;
          }}
        }}
      }}
      host.remove();
      return {{
        name: spec.name,
        width: spec.width,
        height: spec.height,
        scrollWidth,
        clientWidth,
        horizontalOverflow: scrollWidth > clientWidth + 2,
        offscreenCount: offscreen.length,
        offscreen,
        pass: scrollWidth <= clientWidth + 2 && offscreen.length === 0,
      }};
    }}
    (async () => {{
      const results = [];
      for (const spec of cases) {{
        results.push(await runCase(spec));
        await wait(50);
      }}
      document.getElementById('result').textContent = JSON.stringify(results);
    }})();
  </script>
</body>
</html>
"""


def run_browser_probe(browser: str, target_html: str) -> list[dict[str, Any]]:
    probe_html = build_probe_html(target_html)
    with tempfile.TemporaryDirectory(prefix="openspec-workflow-layout-") as tmpdir:
        probe_path = Path(tmpdir) / "probe.html"
        probe_path.write_text(probe_html)
        args = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=7000",
            "--dump-dom",
            probe_path.as_uri(),
        ]
        proc = subprocess.run(args, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            fallback = args.copy()
            fallback[1] = "--headless"
            proc = subprocess.run(fallback, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "browser probe failed").strip())
        match = re.search(r'<pre id="result">([\s\S]*?)</pre>', proc.stdout)
        if not match:
            raise RuntimeError("browser probe did not produce a result payload")
        payload = html.unescape(match.group(1).strip())
        data = json.loads(payload)
        if not isinstance(data, list):
            raise RuntimeError("browser probe result was not a list")
        return data


def validate_source_manifest(change_name: str, change_dir: Path) -> ValidationResult:
    manifest_path = change_dir / "source-manifest.json"
    schema_path = package_root() / "schemas" / "source-manifest.schema.json"
    if not manifest_path.exists():
        return ValidationResult("not_present", {"changeName": change_name})

    manifest = load_json(manifest_path)
    errors = validator_errors(schema_path, manifest)
    if manifest.get("changeName") != change_name:
        errors.append("source-manifest.changeName does not match target change")
    stale, missing = freshness_report(manifest, change_dir)
    if missing:
        errors.append("missing source files referenced by source-manifest.json")

    data: dict[str, Any] = {
        "changeName": change_name,
        "staleCount": len(stale),
        "missingSourceCount": len(missing),
    }
    if stale:
        data["stale"] = stale
    if missing:
        data["missingSources"] = missing
    if errors:
        data["errors"] = errors
        return ValidationResult("fail", data)
    return ValidationResult("ok", data)


def validate_presentation_contract(html_path: Path, policy: ProjectPolicy) -> ValidationResult:
    if not html_path.exists():
        return ValidationResult("no_file", {"htmlFile": str(html_path)})

    text = html_path.read_text()
    lang_match = re.search(r'<html\b[^>]*\blang=["\']([^"\']+)["\']', text, flags=re.IGNORECASE)
    lang_value = lang_match.group(1) if lang_match else ""
    viewport_present = bool(
        re.search(r'<meta\b[^>]*name=["\']viewport["\']', text, flags=re.IGNORECASE)
    )
    lang_ok = lang_value.lower() == policy.change_explainer.locale.lower()
    visible_text = strip_tags(text)
    cjk_count = len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', visible_text))

    fixed_stage_markers: list[str] = []
    if re.search(r'width\s*:\s*1920px', text, flags=re.IGNORECASE):
        fixed_stage_markers.append("width_1920px")
    if re.search(r'(?:height|min-height)\s*:\s*1080px', text, flags=re.IGNORECASE):
        fixed_stage_markers.append("height_1080px")
    if re.search(r'transform-origin\s*:\s*top left', text, flags=re.IGNORECASE):
        fixed_stage_markers.append("transform_origin_top_left")
    if re.search(r'\bscaleDeck\s*\(', text):
        fixed_stage_markers.append("scaleDeck_js")
    if 'id="viewport"' in text and 'id="deck"' in text:
        fixed_stage_markers.append("viewport_deck_ids")

    browser = find_browser()
    browser_status = "not_run"
    browser_cases: list[dict[str, Any]] = []
    browser_error = ""
    skip_env_name = policy.change_explainer.skip_browser_layout_check_env

    if policy.change_explainer.require_viewport_meta and not viewport_present:
        browser_status = "skipped_missing_viewport"
    elif fixed_stage_markers:
        browser_status = "skipped_fixed_stage_detected"
    elif os.environ.get(skip_env_name) == "1":
        browser_status = "skipped_by_env"
    elif browser is None:
        browser_status = "browser_missing"
        browser_error = "Chrome/Chromium is required for layout confirmation"
    else:
        try:
            browser_cases = run_browser_probe(browser, text)
            browser_status = "ok"
        except Exception as err:  # noqa: BLE001
            browser_status = "probe_failed"
            browser_error = str(err)

    errors: list[str] = []
    if not lang_ok:
        errors.append("missing_expected_lang")
    if policy.change_explainer.require_viewport_meta and not viewport_present:
        errors.append("missing_viewport_meta")
    if cjk_count < policy.change_explainer.min_cjk_chars:
        errors.append("insufficient_cjk_copy")
    if fixed_stage_markers:
        errors.append("fixed_stage_layout_detected")
    if browser_status in {"browser_missing", "probe_failed"}:
        errors.append("layout_confirmation_unavailable")
    if browser_cases and any(not bool(case.get("pass")) for case in browser_cases):
        errors.append("layout_overflow_detected")

    data: dict[str, Any] = {
        "htmlFile": str(html_path),
        "htmlLang": lang_value or "missing",
        "expectedLang": policy.change_explainer.locale,
        "viewportMeta": "present" if viewport_present else "missing",
        "cjkCharCount": cjk_count,
        "minimumCjkCharCount": policy.change_explainer.min_cjk_chars,
        "fixedStageMarkers": fixed_stage_markers or ["none"],
        "layoutBrowserStatus": browser_status,
    }
    if browser:
        data["layoutBrowserBin"] = browser
    if browser_cases:
        data["layoutCases"] = browser_cases
    if browser_error:
        data["layoutBrowserError"] = browser_error
    if errors:
        data["errors"] = errors
        return ValidationResult("fail", data)
    return ValidationResult("ok", data)


def validate_explainer_artifact(change_name: str, change_dir: Path, policy: ProjectPolicy) -> ValidationResult:
    html_path = change_dir / "change-explainer.html"
    if not html_path.exists():
        return ValidationResult(
            "fail",
            {
                "changeName": change_name,
                "changeDir": str(change_dir),
                "explainerFile": str(html_path),
                "errors": ["missing_explainer_file"],
            },
        )

    text = html_path.read_text().replace("\r", "")
    missing_markers = [
        section_id
        for section_id in policy.change_explainer.required_sections
        if f'id="{section_id}"' not in text and f"id='{section_id}'" not in text
    ]

    errors: list[str] = []
    if "<html" not in text:
        errors.append("html_root_missing")
    if "<body" not in text:
        errors.append("body_root_missing")
    if missing_markers:
        errors.append("missing_required_markers")
    if not policy.change_explainer.allow_remote_dependencies and REMOTE_DEP_RE.search(text):
        errors.append("remote_runtime_dependency_detected")

    presentation = validate_presentation_contract(html_path, policy)
    manifest = validate_source_manifest(change_name, change_dir)
    if presentation.status != "ok":
        errors.append("invalid_presentation_contract")
    if manifest.status == "fail":
        errors.append("invalid_source_manifest")

    data: dict[str, Any] = {
        "changeName": change_name,
        "changeDir": str(change_dir),
        "explainerFile": str(html_path),
        "presentation": presentation.data,
        "sourceManifest": manifest.data,
    }
    if missing_markers:
        data["missingMarkers"] = missing_markers
    if errors:
        data["errors"] = errors
        return ValidationResult("fail", data)
    return ValidationResult("ok", data)


def find_blocking_tasks(tasks_path: Path, backlog_markers: list[str]) -> TaskCheckResult:
    if not tasks_path.exists():
        return TaskCheckResult(blocking=["tasks.md not found"], backlog=[])

    current_heading = ""
    blocking: list[str] = []
    backlog: list[str] = []
    for raw_line in tasks_path.read_text().splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            current_heading = line.lstrip("#").strip().lower()
            continue
        if line.startswith("- [x]") or line.startswith("- [~]"):
            continue
        if not line.startswith("- [ ]"):
            continue

        lowered = line.lower()
        is_backlog = "[backlog]" in lowered or any(marker in current_heading for marker in backlog_markers)
        if is_backlog:
            backlog.append(line)
        else:
            blocking.append(line)
    return TaskCheckResult(blocking=blocking, backlog=backlog)
