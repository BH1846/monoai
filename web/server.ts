import "dotenv/config";
import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";

const PORT = 3000;
const app = express();

// Enable rich JSON payloads
app.use(express.json({ limit: "50mb" }));

const DEFAULT_GATEWAY_URL = "http://localhost:8000";

function gatewayUrlFor(req: express.Request): string {
  const fromHeader = req.header("x-monoai-gateway-url");
  const base = fromHeader || process.env.MONOAI_GATEWAY_URL || DEFAULT_GATEWAY_URL;
  return base.replace(/\/+$/, "");
}

// REST API Health endpoint (simple liveness of the Express proxy itself)
app.get("/api/health", (req, res) => {
  res.json({ status: "healthy", timestamp: new Date().toISOString() });
});

// Proxies the gateway's own readiness probe -- used by Settings > Test Connection
app.get("/api/health/ready", async (req, res) => {
  const gatewayUrl = gatewayUrlFor(req);
  try {
    const upstream = await fetch(`${gatewayUrl}/health/ready`);
    const data = await upstream.json().catch(() => ({}));
    res.status(upstream.status).json(data);
  } catch (error: any) {
    res.status(502).json({
      status: "not_ready",
      checks: {},
      error: error.message || `Failed to reach gateway at ${gatewayUrl}`,
    });
  }
});

interface GuardrailDecision {
  type: "pii" | "rbac" | "secret" | "vulnerability" | "info" | "system_error";
  status: "blocked" | "redacted" | "neutralized" | "allowed";
  title: string;
  message: string;
  details?: string[];
}

// Matches the type-labeled session-vault placeholder emitted by the gateway's
// PII sanitizer, e.g. <EMAIL_PII_5ba8e23a3f> / <PERSON_PII_7dac3827bb>
// (core/vault/session_tokens.py's TOKEN_RE: <{LABEL}_PII_{10-hex}>, where the
// label is uppercase + underscores). Presence in sanitized_prompt means a
// REVERSIBLE redaction fired. NOTE: keep this in lockstep with the gateway's
// token format -- it was previously the older [PII_TOKEN_xxxxxxxxxx] form, and
// when the gateway moved to type-labeled tokens this regex silently stopped
// matching, so the UI showed "Query Analyzer Passed" on redacted requests.
const PII_TOKEN_RE = /<[A-Z][A-Z_]*_PII_[0-9a-f]{10}>/;

function labelToGuardrailType(labels: string[]): GuardrailDecision["type"] {
  if (labels.includes("SECRET")) return "secret";
  if (labels.includes("PROMPT_INJECTION")) return "vulnerability";
  return "pii";
}

app.post("/api/chat", async (req, res) => {
  try {
    const { messages, model, session_id } = req.body;

    if (!messages || !Array.isArray(messages)) {
      return res.status(400).json({ error: "Invalid request payload. 'messages' array is required." });
    }

    // Flatten client messages (which may carry attachments) into the plain
    // {role, content} shape the gateway's /v1/chat/completions expects.
    // Doc/text attachments are folded into the message content; images are
    // skipped since the gateway is text-only.
    const flatMessages = messages.map((m: any) => {
      let content: string = m.content || "";
      if (Array.isArray(m.attachments)) {
        for (const att of m.attachments) {
          if (att?.text) {
            content += `\n\n[Document Attachment: ${att.name}]\n${att.text}`;
          }
        }
      }
      const role = m.role === "assistant" ? "assistant" : m.role === "system" ? "system" : "user";
      return { role, content };
    });

    const gatewayUrl = gatewayUrlFor(req);
    const virtualKey = req.header("x-monoai-virtual-key") || process.env.MONOAI_VIRTUAL_KEY || "";

    let upstream: Response;
    try {
      upstream = await fetch(`${gatewayUrl}/v1/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${virtualKey}`,
        },
        body: JSON.stringify({ model: model || "auto", messages: flatMessages, session_id }),
      });
    } catch (networkErr: any) {
      return res.json({
        content: `Unable to reach the MonoAI gateway at ${gatewayUrl}. Verify the Gateway URL in Settings and that the gateway is running.`,
        modelUsed: model,
        timestamp: new Date().toISOString(),
        guardrail: {
          type: "system_error",
          status: "blocked",
          title: "Gateway Unreachable",
          message: networkErr.message || "Network error contacting gateway",
        } satisfies GuardrailDecision,
      });
    }

    const data = await upstream.json().catch(() => ({}));

    if (upstream.status === 200) {
      const monoai = data.monoai || {};
      const content = data.choices?.[0]?.message?.content ?? "";
      const redacted = typeof monoai.sanitized_prompt === "string" && PII_TOKEN_RE.test(monoai.sanitized_prompt);

      const commonDetails = [
        `Policy: ${monoai.policy_id ?? "n/a"} v${monoai.policy_version ?? "n/a"}`,
        `Provider: ${monoai.provider ?? "n/a"}`,
        `Difficulty: ${monoai.difficulty ?? "n/a"}`,
        `Cost: $${Number(monoai.cost_usd ?? 0).toFixed(6)}`,
        `Review required: ${monoai.review_required ? "yes" : "no"}`,
      ];

      const guardrail: GuardrailDecision = redacted
        ? {
            type: "pii",
            status: "redacted",
            title: "PII Shield Active — Auto-Redaction Applied",
            message: "Sensitive identifiers were detected and redacted before this request was forwarded to the model.",
            details: [...commonDetails, `Unresolved tokens: ${(monoai.unresolved_tokens ?? []).join(", ") || "none"}`],
          }
        : {
            type: "info",
            status: "allowed",
            title: "Query Analyzer Passed",
            message: "No blocking policy violations detected. Request forwarded to the model.",
            details: commonDetails,
          };

      return res.json({
        content,
        modelUsed: data.model || model,
        timestamp: new Date().toISOString(),
        guardrail,
      });
    }

    if (upstream.status === 422 && data?.error?.type === "blocked_content") {
      const labels: string[] = data.error.labels || [];
      return res.json({
        content: "This request was intercepted and blocked by the MonoAI Policy Gateway. Refer to the policy details in the banner above.",
        modelUsed: model,
        timestamp: new Date().toISOString(),
        guardrail: {
          type: labelToGuardrailType(labels),
          status: "blocked",
          title: "Policy Violation: Content Blocked",
          message: data.error.message || "Blocked by policy.",
          details: labels,
        } satisfies GuardrailDecision,
      });
    }

    // 401 authentication_error / 402 budget_exceeded / 403 model_not_allowed /
    // 429 rate_limited / 503 provider_unavailable, or anything else unexpected.
    const errType: string | undefined = data?.error?.type;
    const message: string = data?.error?.message || `Gateway returned HTTP ${upstream.status}`;
    const details: string[] = [];
    if (data?.error?.retry_after_ms != null) details.push(`Retry after: ${data.error.retry_after_ms}ms`);
    if (data?.error?.allowed_models) details.push(`Allowed models: ${(data.error.allowed_models as string[]).join(", ") || "none"}`);
    if (data?.error?.budget_usd_monthly != null) {
      details.push(`Budget: $${data.error.budget_usd_spent} / $${data.error.budget_usd_monthly}`);
    }
    if (data?.error?.tier) details.push(`Tier: ${data.error.tier}`);

    return res.json({
      content: `Request rejected by the gateway (HTTP ${upstream.status}): ${message}`,
      modelUsed: model,
      timestamp: new Date().toISOString(),
      guardrail: {
        type: upstream.status === 403 ? "rbac" : "system_error",
        status: "blocked",
        title: `Gateway Error ${upstream.status}${errType ? `: ${errType}` : ""}`,
        message,
        details: details.length ? details : undefined,
      } satisfies GuardrailDecision,
    });
  } catch (error: any) {
    console.error("Chat proxy error in server.ts:", error);
    return res.status(500).json({
      error: error.message || "An error occurred while proxying to the MonoAI gateway.",
    });
  }
});

// Lets a chat session introspect its own virtual key (model_allowlist etc.)
// without needing admin access -- used to filter the model picker down to
// only what that key is actually allowed to call.
app.get("/api/me", async (req, res) => {
  const gatewayUrl = gatewayUrlFor(req);
  const virtualKey = req.header("x-monoai-virtual-key") || process.env.MONOAI_VIRTUAL_KEY || "";
  try {
    const upstream = await fetch(`${gatewayUrl}/v1/me`, {
      headers: { Authorization: `Bearer ${virtualKey}` },
    });
    const text = await upstream.text();
    res.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    if (contentType) res.setHeader("content-type", contentType);
    res.send(text);
  } catch (error: any) {
    res.status(502).json({
      error: { type: "proxy_error", message: error.message || `Failed to reach gateway at ${gatewayUrl}` },
    });
  }
});

// Scans an uploaded file for PII (gateway/api/files.py POST /v1/files/scan):
// extracts text (OCR for images/scanned PDFs), detects PII, returns the
// redacted text + findings. Attached to the caller's own virtual key so the
// file is scanned under that key's policy.
app.post("/api/files/scan", async (req, res) => {
  const gatewayUrl = gatewayUrlFor(req);
  const virtualKey = req.header("x-monoai-virtual-key") || process.env.MONOAI_VIRTUAL_KEY || "";
  try {
    const upstream = await fetch(`${gatewayUrl}/v1/files/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${virtualKey}` },
      body: JSON.stringify(req.body ?? {}),
    });
    const text = await upstream.text();
    res.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    if (contentType) res.setHeader("content-type", contentType);
    res.send(text);
  } catch (error: any) {
    res.status(502).json({
      error: { type: "proxy_error", message: error.message || `Failed to reach gateway at ${gatewayUrl}` },
    });
  }
});

// Self-serve account creation/login (see gateway/api/auth.py): unauthenticated
// passthrough -- these two routes are how a browser gets a virtual key in the
// first place, so there's no admin/virtual key to attach yet.
app.post("/api/auth/register", async (req, res) => {
  const gatewayUrl = gatewayUrlFor(req);
  try {
    const upstream = await fetch(`${gatewayUrl}/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body ?? {}),
    });
    const text = await upstream.text();
    res.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    if (contentType) res.setHeader("content-type", contentType);
    res.send(text);
  } catch (error: any) {
    res.status(502).json({
      error: { type: "proxy_error", message: error.message || `Failed to reach gateway at ${gatewayUrl}` },
    });
  }
});

app.post("/api/auth/login", async (req, res) => {
  const gatewayUrl = gatewayUrlFor(req);
  try {
    const upstream = await fetch(`${gatewayUrl}/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body ?? {}),
    });
    const text = await upstream.text();
    res.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    if (contentType) res.setHeader("content-type", contentType);
    res.send(text);
  } catch (error: any) {
    res.status(502).json({
      error: { type: "proxy_error", message: error.message || `Failed to reach gateway at ${gatewayUrl}` },
    });
  }
});

// Lets a chat session list which admin-registered models it's allowed to
// call, without needing admin access -- populates the model picker/directory
// for a regular virtual-key-only user (see gateway/api/chat.py GET /v1/models).
app.get("/api/models", async (req, res) => {
  const gatewayUrl = gatewayUrlFor(req);
  const virtualKey = req.header("x-monoai-virtual-key") || process.env.MONOAI_VIRTUAL_KEY || "";
  try {
    const upstream = await fetch(`${gatewayUrl}/v1/models`, {
      headers: { Authorization: `Bearer ${virtualKey}` },
    });
    const text = await upstream.text();
    res.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    if (contentType) res.setHeader("content-type", contentType);
    res.send(text);
  } catch (error: any) {
    res.status(502).json({
      error: { type: "proxy_error", message: error.message || `Failed to reach gateway at ${gatewayUrl}` },
    });
  }
});

// Powers the Admin > Audit Log tab. The real audit trail lives at
// GET /v1/evidence/export (gateway/api/evidence.py) rather than under
// /v1/admin/*, so it needs its own route ahead of the generic passthrough
// below -- and unlike that passthrough, this gates on the admin key itself
// (evidence.py's endpoint doesn't check auth -- it's built for offline
// signature verification by a third party) rather than trusting the browser.
// The bundle is hash-chained NDJSON (first line: manifest, rest: one
// AuditRecord per line) -- flattened here into the AuditEvent[] shape
// AuditLogTab.tsx already renders.
app.get("/api/admin/audit-log", async (req, res) => {
  const gatewayUrl = gatewayUrlFor(req);
  const adminKey = req.header("x-monoai-admin-key") || process.env.MONOAI_ADMIN_KEY || "";
  if (!adminKey) {
    return res.status(401).json({ error: { type: "unauthorized", message: "admin key required" } });
  }

  try {
    const upstream = await fetch(`${gatewayUrl}/v1/evidence/export`, {
      headers: { Authorization: `Bearer ${adminKey}` },
    });
    if (!upstream.ok) {
      const body = await upstream.text().catch(() => "");
      return res.status(upstream.status).json({ error: { type: "proxy_error", message: body || `HTTP ${upstream.status}` } });
    }
    const text = await upstream.text();
    const lines = text.split("\n").filter((l) => l.trim().length > 0);
    // First line is {"record_count", "chain_verified"}, not a record -- skip it.
    const records = lines.slice(1).map((l) => JSON.parse(l));

    const events = records.map((r: any) => {
      const labels = Object.keys(r.span_counts_by_label || {}).concat(r.blocked_labels || []);
      const rule: string = labels.some((l) => l === "SECRET")
        ? "SECRET_SCAN"
        : labels.some((l) => l === "PROMPT_INJECTION")
          ? "CODE_VULN"
          : "PII_SCAN";
      const decision: string =
        r.event === "blocked" ? "BLOCKED" : (r.redacted_count || 0) > 0 ? "REDACTED" : "ALLOWED";
      const detailParts = [`event=${r.event}`];
      if (r.blocked_labels?.length) detailParts.push(`blocked=[${r.blocked_labels.join(", ")}]`);
      if (r.redacted_count) detailParts.push(`redacted_spans=${r.redacted_count}`);
      if (r.provider) detailParts.push(`provider=${r.provider}`);
      if (r.router_tier) detailParts.push(`tier=${r.router_tier}`);
      if (r.cost_usd) detailParts.push(`cost=$${Number(r.cost_usd).toFixed(4)}`);

      return {
        id: r.request_id,
        timestamp: new Date((r.ts || 0) * 1000).toISOString(),
        decision,
        rule,
        user: r.team_id || r.virtual_key_id || "unknown",
        model: r.model_id || r.difficulty || "n/a",
        detail: detailParts.join(" · "),
      };
    }).reverse(); // newest first

    res.json({ events });
  } catch (error: any) {
    res.status(502).json({
      error: { type: "proxy_error", message: error.message || `Failed to reach gateway at ${gatewayUrl}` },
    });
  }
});

// Generic admin passthrough: forwards method/path-suffix/query/body to the
// gateway's /v1/admin/* surface, injecting the admin bearer server-side so it
// never has to touch the browser beyond this same-origin proxy.
app.all("/api/admin/*", async (req, res) => {
  const gatewayUrl = gatewayUrlFor(req);
  const adminKey = req.header("x-monoai-admin-key") || process.env.MONOAI_ADMIN_KEY || "";
  const suffix = req.path.replace(/^\/api\/admin\//, "");
  const queryString = new URLSearchParams(req.query as Record<string, string>).toString();
  const target = `${gatewayUrl}/v1/admin/${suffix}${queryString ? `?${queryString}` : ""}`;

  const init: RequestInit = {
    method: req.method,
    headers: {
      Authorization: `Bearer ${adminKey}`,
      "Content-Type": "application/json",
    },
  };
  if (!["GET", "HEAD"].includes(req.method)) {
    init.body = JSON.stringify(req.body ?? {});
  }

  try {
    const upstream = await fetch(target, init);
    const text = await upstream.text();
    res.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    if (contentType) res.setHeader("content-type", contentType);
    res.send(text);
  } catch (error: any) {
    res.status(502).json({
      error: { type: "proxy_error", message: error.message || `Failed to reach gateway at ${gatewayUrl}` },
    });
  }
});

// Configure development server and production static asset serving
async function bootstrap() {
  if (process.env.NODE_ENV !== "production") {
    console.log("Starting server in development mode with Vite middleware...");
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    console.log("Starting server in production mode...");
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server is running on http://localhost:${PORT}`);
  });
}

bootstrap().catch((err) => {
  console.error("Failed to bootstrap application server:", err);
  process.exit(1);
});
