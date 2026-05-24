import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { StringEnum } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import {
  DEFAULT_MAX_BYTES,
  DEFAULT_MAX_LINES,
  formatSize,
  truncateHead,
} from "@earendil-works/pi-coding-agent";
import { Text } from "@earendil-works/pi-tui";
import { Type } from "typebox";

type WorkflowAction =
  | "propose"
  | "build-source-manifest"
  | "generate-explainer"
  | "validate-explainer"
  | "validate-source-manifest"
  | "archive-preflight";

type WorkflowRun = {
  action: WorkflowAction;
  projectRoot: string;
  changeName: string;
  backend?: "template" | "opendesign";
  exitCode: number;
  truncated: boolean;
  output: string;
  fullOutputBytes: number;
  fullOutputLines: number;
};

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, "../..");
const SKILLS_DIR = resolve(REPO_ROOT, "skills");
const PROMPTS_DIR = resolve(REPO_ROOT, "prompts");
const SCRIPTS_DIR = resolve(REPO_ROOT, "scripts");
const CUSTOM_MESSAGE_TYPE = "openspec-workflow";
const LONG_TIMEOUT_MS = 30 * 60 * 1000;

const ACTION_TO_SCRIPT: Record<WorkflowAction, string> = {
  propose: "openspec-propose",
  "build-source-manifest": "openspec-build-source-manifest",
  "generate-explainer": "openspec-generate-explainer",
  "validate-explainer": "openspec-validate-explainer",
  "validate-source-manifest": "openspec-validate-source-manifest",
  "archive-preflight": "openspec-archive-preflight",
};

const ACTION_LABELS: Record<WorkflowAction, string> = {
  propose: "Propose",
  "build-source-manifest": "Build Source Manifest",
  "generate-explainer": "Generate Explainer",
  "validate-explainer": "Validate Explainer",
  "validate-source-manifest": "Validate Source Manifest",
  "archive-preflight": "Archive Preflight",
};

function splitArgs(raw: string): string[] {
  const tokens: string[] = [];
  const re = /"([^"\\]*(?:\\.[^"\\]*)*)"|'([^'\\]*(?:\\.[^'\\]*)*)'|(\S+)/g;
  for (const match of raw.matchAll(re)) {
    const value = match[1] ?? match[2] ?? match[3] ?? "";
    tokens.push(value.replace(/\\([\\"'])/g, "$1"));
  }
  return tokens;
}

function hasFlag(args: string[], flag: string): boolean {
  return args.includes(flag) || args.some((arg) => arg.startsWith(`${flag}=`));
}

function buildScriptArgs(action: WorkflowAction, params: { changeName: string; backend?: string; projectRoot?: string }, cwd: string): string[] {
  const args = [params.changeName];
  if ((action === "propose" || action === "generate-explainer") && params.backend) {
    args.push("--backend", params.backend);
  }
  args.push("--project-root", params.projectRoot || cwd);
  return args;
}

function summariseRun(run: WorkflowRun): string {
  const status = run.exitCode === 0 ? "ok" : `failed (${run.exitCode})`;
  return `${ACTION_LABELS[run.action]} · ${run.changeName} · ${status}`;
}

function formatOutput(stdout: string, stderr: string): { text: string; totalBytes: number; totalLines: number; truncated: boolean } {
  const raw = [stdout.trimEnd(), stderr.trimEnd()].filter(Boolean).join("\n\n");
  const truncation = truncateHead(raw || "(no output)", {
    maxLines: DEFAULT_MAX_LINES,
    maxBytes: DEFAULT_MAX_BYTES,
  });

  let text = truncation.content;
  if (truncation.truncated) {
    text += `\n\n[Output truncated: ${truncation.outputLines} of ${truncation.totalLines} lines (${formatSize(
      truncation.outputBytes,
    )} of ${formatSize(truncation.totalBytes)})]`;
  }

  return {
    text,
    totalBytes: truncation.totalBytes,
    totalLines: truncation.totalLines,
    truncated: truncation.truncated,
  };
}

async function runWorkflowScript(
  pi: ExtensionAPI,
  action: WorkflowAction,
  args: string[],
  ctx: ExtensionContext | ExtensionCommandContext,
): Promise<WorkflowRun> {
  const result = await pi.exec(resolve(SCRIPTS_DIR, ACTION_TO_SCRIPT[action]), args, {
    signal: ctx.signal,
    timeout: LONG_TIMEOUT_MS,
  });

  const formatted = formatOutput(result.stdout ?? "", result.stderr ?? "");
  return {
    action,
    projectRoot: args[args.indexOf("--project-root") + 1] ?? ctx.cwd,
    changeName: args[0],
    backend: args.includes("--backend") ? (args[args.indexOf("--backend") + 1] as "template" | "opendesign") : undefined,
    exitCode: result.code,
    truncated: formatted.truncated,
    output: formatted.text,
    fullOutputBytes: formatted.totalBytes,
    fullOutputLines: formatted.totalLines,
  };
}

async function ensureCommandArgs(
  action: WorkflowAction,
  rawArgs: string,
  ctx: ExtensionCommandContext,
): Promise<string[] | null> {
  if (rawArgs.trim()) {
    return splitArgs(rawArgs);
  }

  const prompt =
    action === "propose"
      ? "Change name (kebab-case), optional flags after it"
      : "Change name, optional flags after it";
  const value = await ctx.ui.input(`OpenSpec ${ACTION_LABELS[action]}`, prompt);
  if (!value?.trim()) {
    return null;
  }
  return splitArgs(value);
}

function emitWorkflowMessage(pi: ExtensionAPI, run: WorkflowRun): void {
  pi.sendMessage({
    customType: CUSTOM_MESSAGE_TYPE,
    content: summariseRun(run),
    display: true,
    details: run,
  });
}

function registerPiCommands(pi: ExtensionAPI): void {
  const register = (action: WorkflowAction, name: string, description: string) => {
    pi.registerCommand(name, {
      description,
      handler: async (rawArgs, ctx) => {
        const pieces = await ensureCommandArgs(action, rawArgs, ctx);
        if (!pieces || pieces.length === 0) {
          return;
        }

        const args = [...pieces];
        if (!hasFlag(args, "--project-root")) {
          args.push("--project-root", ctx.cwd);
        }

        const run = await runWorkflowScript(pi, action, args, ctx);
        emitWorkflowMessage(pi, run);
        ctx.ui.notify(
          run.exitCode === 0 ? summariseRun(run) : `OpenSpec workflow failed: ${summariseRun(run)}`,
          run.exitCode === 0 ? "info" : "error",
        );
      },
    });
  };

  register("propose", "openspec-propose", "Scaffold a new governed change package in the current project");
  register(
    "build-source-manifest",
    "openspec-build-source-manifest",
    "Regenerate source-manifest.json for a change in the current project",
  );
  register(
    "generate-explainer",
    "openspec-generate-explainer",
    "Generate or regenerate change-explainer.html for a change in the current project",
  );
  register(
    "validate-explainer",
    "openspec-validate-explainer",
    "Validate change-explainer.html for a change in the current project",
  );
  register(
    "validate-source-manifest",
    "openspec-validate-source-manifest",
    "Validate source-manifest.json for a change in the current project",
  );
  register(
    "archive-preflight",
    "openspec-archive-preflight",
    "Run archive-readiness checks for a change in the current project",
  );
}

export default function openspecWorkflowPiAdapter(pi: ExtensionAPI) {
  pi.on("resources_discover", async () => ({
    skillPaths: [SKILLS_DIR],
    promptPaths: [PROMPTS_DIR],
  }));

  pi.registerMessageRenderer(CUSTOM_MESSAGE_TYPE, (message, options, theme) => {
    const text = [
      theme.fg("toolTitle", theme.bold(`${message.content}`)),
      theme.fg("muted", "Use the shared workflow scripts; this adapter only wraps them."),
    ];

    if (options.expanded && message.details && typeof message.details === "object") {
      const details = message.details as Partial<WorkflowRun>;
      if (details.output) {
        text.push("");
        text.push(theme.fg("dim", details.output));
      }
    }

    return new Text(text.join("\n"), 0, 0);
  });

  registerPiCommands(pi);

  pi.registerTool({
    name: "openspec_workflow",
    label: "OpenSpec Workflow",
    description:
      "Run shared openspec workflow commands (propose, build-source-manifest, generate-explainer, validate-explainer, validate-source-manifest, archive-preflight) against the current project or an explicit project root.",
    promptSnippet:
      "Run openspec workflow commands against the current project root or an explicit target project root.",
    promptGuidelines: [
      "Use openspec_workflow when the user asks to scaffold or validate an OpenSpec-style change package instead of reimplementing the workflow in ad hoc shell commands.",
    ],
    parameters: Type.Object({
      action: StringEnum([
        "propose",
        "build-source-manifest",
        "generate-explainer",
        "validate-explainer",
        "validate-source-manifest",
        "archive-preflight",
      ] as const),
      changeName: Type.String({ description: "Change name in kebab-case" }),
      backend: Type.Optional(StringEnum(["template", "opendesign"] as const)),
      projectRoot: Type.Optional(Type.String({ description: "Target project root. Defaults to the current cwd." })),
    }),
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const action = params.action as WorkflowAction;
      const args = buildScriptArgs(
        action,
        {
          changeName: params.changeName,
          backend: params.backend,
          projectRoot: params.projectRoot,
        },
        ctx.cwd,
      );
      const run = await runWorkflowScript(pi, action, args, ctx);
      if (run.exitCode !== 0) {
        throw new Error(`${summariseRun(run)}\n\n${run.output}`);
      }
      return {
        content: [
          {
            type: "text",
            text: `${summariseRun(run)}\n\n${run.output}`,
          },
        ],
        details: run,
      };
    },
  });
}
