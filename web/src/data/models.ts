import { ModelOption } from '../types';

// The only entry in this catalog -- every other model shown in the UI comes
// live from the gateway's provider/model registry (admin-configured via the
// Providers tab, fetched via GET /v1/models), not a hardcoded list.
export const ENTERPRISE_MODELS: ModelOption[] = [
  {
    id: 'auto',
    name: 'Auto-Routing Gateway',
    tag: 'Dynamic Routing',
    description: 'Uses the gateway\'s heuristic difficulty classifier to route each request to the simple/moderate/complex model tier configured via MONOAI_PROVIDER (see gateway/config.py).',
    isPaid: false,
    provider: 'Torkq',
    latency: '—',
    costPerMillion: '—',
    contextWindow: '—',
    guardrails: ['Gateway-enforced policy (PII / secrets / prompt injection)'],
    status: 'Approved'
  }
];
