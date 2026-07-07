import { ModelOption } from '../types';

export const ENTERPRISE_MODELS: ModelOption[] = [
  // --- ENTERPRISE ORCHESTRATION ---
  {
    id: 'auto',
    name: 'Auto-Routing Gateway',
    tag: 'Dynamic Routing',
    description: 'Intelligent orchestrator. Dynamically analyzes incoming prompt structures, language complexity, security parameters, and coding constraints to automatically forward requests to the most optimal enterprise model path.',
    isPaid: false,
    provider: 'Enterprise',
    latency: '68ms - 194ms',
    costPerMillion: 'Dynamic (Optimized)',
    contextWindow: 'Dynamic (Up to 2.0M)',
    guardrails: ['Dynamic Intent Analysis', 'Automatic Route Optimization', 'DLP Shields', 'RBAC Enforcement'],
    status: 'Approved'
  },
  // --- GEMINI SUITE ---
  {
    id: 'gemini-3.5-flash',
    name: 'Gemini 3.5 Flash',
    tag: 'Ultra-Fast',
    description: 'Next-generation lightweight model designed for high-frequency, low-latency enterprise tasks. Optimized for rapid data processing and tool call delegation.',
    isPaid: false,
    provider: 'Gemini',
    latency: '102ms',
    costPerMillion: '$0.075 / $0.30',
    contextWindow: '1.0M',
    guardrails: ['PII Redaction', 'Secret Scanning', 'RBAC Enforcement'],
    status: 'Approved'
  },
  {
    id: 'gemini-3.1-pro-preview',
    name: 'Gemini 3.1 Pro Preview',
    tag: 'Complex Logic',
    description: 'State-of-the-art preview model optimized for heavy multi-turn reasoning, mathematical tasks, and complex programming scenarios.',
    isPaid: true,
    provider: 'Gemini',
    latency: '185ms',
    costPerMillion: '$1.25 / $5.00',
    contextWindow: '2.0M',
    guardrails: ['PII Redaction', 'Secret Scanning', 'RBAC Enforcement', 'Vulnerability Neutralizer'],
    status: 'Approved'
  },
  {
    id: 'gemini-1.5-pro',
    name: 'Gemini 1.5 Pro',
    tag: 'Deep Context',
    description: 'Production-grade foundation model offering unparalleled context window capacities, perfect for processing entire multi-file codebases and compliance sheets.',
    isPaid: true,
    provider: 'Gemini',
    latency: '194ms',
    costPerMillion: '$1.25 / $5.00',
    contextWindow: '2.0M',
    guardrails: ['PII Redaction', 'Secret Scanning', 'RBAC Enforcement', 'SQL Injection check'],
    status: 'Approved'
  },
  {
    id: 'gemini-1.5-flash',
    name: 'Gemini 1.5 Flash',
    tag: 'High-Throughput',
    description: 'High-speed efficiency model designed for bulk processing, high concurrency, and massive translation pipeline operations under strict latency SLAs.',
    isPaid: false,
    provider: 'Gemini',
    latency: '94ms',
    costPerMillion: '$0.075 / $0.30',
    contextWindow: '1.0M',
    guardrails: ['PII Redaction', 'Secret Scanning'],
    status: 'Approved'
  },

  // --- OPENAI SUITE ---
  {
    id: 'gpt-4o',
    name: 'GPT-4o (Omni)',
    tag: 'SOTA Omni',
    description: 'OpenAI flagship multi-modal model. Balanced, highly intelligent, and versatile across creative copy, logic, and structured JSON generation.',
    isPaid: true,
    provider: 'OpenAI',
    latency: '138ms',
    costPerMillion: '$2.50 / $10.00',
    contextWindow: '128k',
    guardrails: ['PII Redaction', 'Secret Scanning', 'RBAC Scope Check', 'SQL Injection check'],
    status: 'Approved'
  },
  {
    id: 'gpt-4o-mini',
    name: 'GPT-4o Mini',
    tag: 'High-Efficiency',
    description: 'Lightweight flagship variation offering superb reasoning at a fraction of the computation costs. Ideal for simple filtering and routing agents.',
    isPaid: false,
    provider: 'OpenAI',
    latency: '82ms',
    costPerMillion: '$0.15 / $0.60',
    contextWindow: '128k',
    guardrails: ['PII Redaction', 'Secret Scanning'],
    status: 'Approved'
  },
  {
    id: 'gpt-4',
    name: 'GPT-4 (Legacy)',
    tag: 'Restricted',
    description: 'Legacy OpenAI model with high API fee overheads. Usage is discouraged and restricted to specific backwards-compatible internal platforms.',
    isPaid: true,
    provider: 'OpenAI',
    latency: '310ms',
    costPerMillion: '$30.00 / $60.00',
    contextWindow: '8k',
    guardrails: ['Strict DLP Redaction', 'Secret Scanning', 'Strict RBAC Enforcement'],
    status: 'Restricted'
  },
  {
    id: 'o1-pro',
    name: 'OpenAI o1 Pro',
    tag: 'Reasoning Heavy',
    description: 'Advanced reasoning model utilizing internal reinforcement learning step-by-step thinking processes. High latency but exceptional accuracy.',
    isPaid: true,
    provider: 'OpenAI',
    latency: '1420ms',
    costPerMillion: '$15.00 / $60.00',
    contextWindow: '200k',
    guardrails: ['PII Redaction', 'Secret Scanning', 'Reasoning Trace Audit', 'RBAC Enforcement'],
    status: 'Restricted'
  },
  {
    id: 'o1-mini',
    name: 'OpenAI o1 Mini',
    tag: 'Reasoning Light',
    description: 'Faster, cost-effective reasoning model designed for coding tasks and logical structures that need step-by-step resolution.',
    isPaid: true,
    provider: 'OpenAI',
    latency: '420ms',
    costPerMillion: '$3.00 / $12.00',
    contextWindow: '128k',
    guardrails: ['PII Redaction', 'Secret Scanning', 'Reasoning Trace Audit'],
    status: 'Approved'
  },

  // --- ANTHROPIC CLAUDE SUITE ---
  {
    id: 'claude-3-5-sonnet',
    name: 'Claude 3.5 Sonnet',
    tag: 'Developer Favorite',
    description: 'Anthropic leading engine. Highly praised for state-of-the-art coding abilities, complex technical prose, and high-fidelity artifact creation.',
    isPaid: true,
    provider: 'Claude',
    latency: '162ms',
    costPerMillion: '$3.00 / $15.00',
    contextWindow: '200k',
    guardrails: ['PII Redaction', 'Secret Scanning', 'Prompt Injection Check'],
    status: 'Approved'
  },
  {
    id: 'claude-3-opus',
    name: 'Claude 3 Opus',
    tag: 'Restricted',
    description: 'Deep analytical model with excellent long-text understanding. Restricted due to high API cost and moderate latency bounds.',
    isPaid: true,
    provider: 'Claude',
    latency: '460ms',
    costPerMillion: '$15.00 / $75.00',
    contextWindow: '200k',
    guardrails: ['PII Redaction', 'Secret Scanning', 'Strict RBAC Scope'],
    status: 'Restricted'
  },
  {
    id: 'claude-3-5-haiku',
    name: 'Claude 3.5 Haiku',
    tag: 'Fast Edge',
    description: 'Fastest Anthropic model. Combines strong reasoning speeds with low price points, making it highly competitive for real-time customer tooling.',
    isPaid: false,
    provider: 'Claude',
    latency: '88ms',
    costPerMillion: '$0.80 / $4.00',
    contextWindow: '200k',
    guardrails: ['PII Redaction', 'Secret Scanning'],
    status: 'Approved'
  },

  // --- GROK SUITE ---
  {
    id: 'grok-2',
    name: 'Grok 2',
    tag: 'Auditing Stage',
    description: 'X.AI state-of-the-art model. Undergoing internal compliance audit to check for toxic payload propagation and security bounds alignment.',
    isPaid: true,
    provider: 'Grok',
    latency: '210ms',
    costPerMillion: '$2.00 / $10.00',
    contextWindow: '128k',
    guardrails: ['PII Redaction', 'Secret Scanning', 'Compliance Checks'],
    status: 'Under Audit'
  },
  {
    id: 'grok-2-mini',
    name: 'Grok 2 Mini',
    tag: 'Auditing Stage',
    description: 'Compact, high-speed iteration of Grok. Currently in sandbox audit to align security telemetry and proxy logs before wide release.',
    isPaid: false,
    provider: 'Grok',
    latency: '115ms',
    costPerMillion: '$0.20 / $0.90',
    contextWindow: '128k',
    guardrails: ['PII Redaction', 'Secret Scanning'],
    status: 'Under Audit'
  },
  {
    id: 'grok-beta',
    name: 'Grok Beta',
    tag: 'Experimental',
    description: 'Highly experimental research branch. Subject to frequent upstream updates and transient downtime. Restricted to R&D departments.',
    isPaid: true,
    provider: 'Grok',
    latency: '175ms',
    costPerMillion: '$2.00 / $10.00',
    contextWindow: '128k',
    guardrails: ['Strict DLP Redaction', 'Secret Scanning', 'RBAC Enforcement'],
    status: 'Restricted'
  },

  // --- OPEN SOURCE & REGIONAL ---
  {
    id: 'llama-3-3-70b',
    name: 'Llama 3.3 70B',
    tag: 'Self-Hosted',
    description: 'Meta open foundation model hosted on our private secure GPU cluster. Outstanding general performance with zero outbound external data leakage risk.',
    isPaid: false,
    provider: 'Meta',
    latency: '118ms',
    costPerMillion: '$0.35 / $0.35',
    contextWindow: '128k',
    guardrails: ['PII Redaction', 'Secret Scanning', 'Model Inversion block'],
    status: 'Approved'
  },
  {
    id: 'deepseek-v3',
    name: 'DeepSeek V3',
    tag: 'Mixture of Experts',
    description: 'Highly efficient MoE architecture offering superb math and coding logic at exceptionally low infrastructure price bounds. Under active compliance scrutiny.',
    isPaid: false,
    provider: 'DeepSeek',
    latency: '235ms',
    costPerMillion: '$0.14 / $0.28',
    contextWindow: '128k',
    guardrails: ['PII Redaction', 'Compliance checks', 'Host Sovereignty verify'],
    status: 'Under Audit'
  },
  {
    id: 'mistral-large',
    name: 'Mistral Large 2',
    tag: 'Sovereign EU',
    description: 'Sovereign European AI capability. Excellent multilingual compliance and native structure alignment with EU data privacy standards.',
    isPaid: true,
    provider: 'Mistral',
    latency: '180ms',
    costPerMillion: '$2.00 / $6.00',
    contextWindow: '128k',
    guardrails: ['PII Redaction', 'Secret Scanning', 'EU GDPR Sovereign Lock'],
    status: 'Approved'
  }
];
