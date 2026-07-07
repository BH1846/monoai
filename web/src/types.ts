export interface Attachment {
  id: string;
  name: string;
  size: string;
  type: string;
  url?: string;
  base64?: string; // used for image processing with Gemini
  text?: string;   // parsed text contents for docs
}

export interface GuardrailDecision {
  type: 'pii' | 'rbac' | 'secret' | 'vulnerability' | 'info' | 'system_error';
  status: 'blocked' | 'redacted' | 'neutralized' | 'allowed';
  title: string;
  message: string;
  details?: string[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  attachments?: Attachment[];
  guardrail?: GuardrailDecision;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  model: string;
  timestamp: string;
}

// Widened to `string` (was a fixed literal union of mock model ids) because
// the chat model picker now also lists model_ids registered live against the
// gateway's provider/model registry, which aren't known at compile time.
export type ModelType = string;

export interface Artifact {
  id: string;
  title: string;
  language: string;
  code: string;
  type: 'code' | 'document' | 'preview';
}

export interface ModelOption {
  id: ModelType;
  name: string;
  tag: string;
  description: string;
  isPaid: boolean;
  // Widened to `string` (was a fixed enum of mock provider brands) because
  // real entries are backed by admin-registered providers with arbitrary
  // names (gateway/providers/registry_store.py), not a fixed catalog.
  provider: string;
  latency: string;
  costPerMillion: string;
  contextWindow: string;
  guardrails: string[];
  status: 'Approved' | 'Restricted' | 'Under Audit';
}

export type AdminTab = 'overview' | 'audit' | 'rbac' | 'guardrails' | 'users' | 'providers' | 'settings';

// ---- Real backend-backed admin records (gateway/api/admin.py) ----

export interface ProviderRecord {
  provider_id: string;
  name: string;
  kind: 'openai-compatible' | 'ollama' | string;
  base_url: string;
  key_last4: string | null;
  enabled: boolean;
}

export interface ModelRecord {
  model_id: string;
  provider_id: string;
  provider_name: string;
  upstream_model: string;
  display_name: string | null;
  enabled: boolean;
}

export interface VirtualKeyRecord {
  key_id: string;
  team_id: string | null;
  policy_id: string;
  model_allowlist: string[] | null;
  budget_usd_monthly: number | null;
  budget_usd_spent: number;
  rate_limit_rps: number;
  rate_limit_burst: number;
  active: boolean;
  created_at: number;
  revoked_at: number | null;
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  decision: 'BLOCKED' | 'REDACTED' | 'ALLOWED';
  rule: 'RBAC' | 'PII_SCAN' | 'SECRET_SCAN' | 'CODE_VULN';
  user: string;
  model: string;
  detail: string;
}

export interface UserRecord {
  id: string;
  name: string;
  email: string;
  role: string;
  lastActive: string;
  status: 'active' | 'disabled';
  totalCost: number;     // accumulated cost in USD
  costLimit: number;     // monthly limit in USD
  inputTokens: number;   // total input tokens consumed
  outputTokens: number;  // total output tokens consumed
}

export interface RbacMatrix {
  [role: string]: {
    [modelOrCapability: string]: boolean;
  };
}

export interface UserPromptTransaction {
  id: string;
  timestamp: string;
  model: string;
  originalPrompt: string;
  redactedPrompt: string;
  llmReply: string;
  rehydratedReply: string;
  status: 'clean' | 'redacted' | 'blocked';
  redactionRulesTriggered: string[];
  inputTokens: number;
  outputTokens: number;
  cost: number;
}

