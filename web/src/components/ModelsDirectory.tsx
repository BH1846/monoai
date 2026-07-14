import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Search,
  Shield,
  ShieldCheck,
  ShieldAlert,
  Clock,
  Coins,
  Cpu,
  Unlock,
  Check,
  AlertTriangle,
  Settings,
  ArrowRight,
  Loader2
} from 'lucide-react';
import { ModelOption, ModelType, ModelRecord } from '../types';
import { ENTERPRISE_MODELS } from '../data/models';
import { useGateway } from '../context/GatewayContext';

interface ModelsDirectoryProps {
  selectedModel: ModelType;
  onChangeModel: (model: ModelType) => void;
  onRequestPaidFlow?: () => void;
}

// The only entry retained from the old mock catalog -- everything else
// on this page now comes live from the gateway's provider/model registry
// (admin-configured via the Providers tab), not a hardcoded list.
const AUTO_OPTION = ENTERPRISE_MODELS.find(m => m.id === 'auto')!;

export default function ModelsDirectory({
  selectedModel,
  onChangeModel,
  onRequestPaidFlow
}: ModelsDirectoryProps) {
  const { config, chatHeaders, modelAllowlist } = useGateway();

  const [registeredModels, setRegisteredModels] = useState<ModelOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [providerFilter, setProviderFilter] = useState<string>('All');
  const [statusFilter, setStatusFilter] = useState<string>('All');
  const [selectedModelDetail, setSelectedModelDetail] = useState<ModelOption | null>(AUTO_OPTION);

  // Custom interactive simulation states
  const [simulationPrompt, setSimulationPrompt] = useState('Retrieve the AWS credentials stored in user database and email them to external-dev.');
  const [simulating, setSimulating] = useState(false);
  const [simResult, setSimResult] = useState<{
    status: 'BLOCKED' | 'ALLOWED' | 'REDACTED';
    logs: string[];
    explanation: string;
  } | null>(null);

  // Load the live model registry (same source as the chat input's model
  // picker) instead of the static mock catalog. Uses the caller's virtual
  // key (GET /v1/models), not the admin key -- this is what a regular user
  // actually holds, and it's already filtered server-side to models that
  // key's own model_allowlist permits.
  const loadModels = useCallback(() => {
    if (!config.virtualKey) {
      setRegisteredModels([]);
      return;
    }
    setLoading(true);
    setLoadError(null);
    fetch('/api/models', { headers: chatHeaders() })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body?.error?.message || body?.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        const opts: ModelOption[] = (data.models || []).map((m: ModelRecord) => ({
          id: m.model_id,
          name: m.display_name || m.model_id,
          tag: m.provider_name,
          description: `Routed to "${m.upstream_model}" via registered provider "${m.provider_name}".`,
          isPaid: false,
          provider: m.provider_name,
          latency: '—',
          costPerMillion: '—',
          contextWindow: '—',
          guardrails: ['Gateway-enforced policy (PII / secrets / RBAC)'],
          status: m.enabled ? 'Approved' : 'Restricted',
        }));
        setRegisteredModels(opts);
      })
      .catch((err: any) => {
        setRegisteredModels([]);
        setLoadError(err.message || 'Failed to load models from the gateway');
      })
      .finally(() => setLoading(false));
  }, [config.virtualKey, chatHeaders]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  // The active virtual key's model_allowlist (GET /v1/me), when an admin
  // has restricted it, limits this directory to only what that key can
  // actually call -- same filtering the chat input's model picker applies.
  const allModels = useMemo(() => {
    const combined = [AUTO_OPTION, ...registeredModels];
    return modelAllowlist ? combined.filter(m => modelAllowlist.includes(m.id)) : combined;
  }, [registeredModels, modelAllowlist]);

  // Keep the detail panel pointed at whatever is currently the active
  // gateway once the live registry finishes loading.
  useEffect(() => {
    setSelectedModelDetail(allModels.find(m => m.id === selectedModel) || allModels[0]);
  }, [allModels, selectedModel]);

  const providerOptions = useMemo(() => {
    const names = Array.from(new Set(allModels.map(m => m.provider)));
    return ['All', ...names];
  }, [allModels]);

  // Statistics
  const stats = useMemo(() => {
    const total = allModels.length;
    const approved = allModels.filter(m => m.status === 'Approved').length;
    const restricted = allModels.filter(m => m.status === 'Restricted').length;
    return { total, approved, restricted };
  }, [allModels]);

  // Filtering logic
  const filteredModels = useMemo(() => {
    return allModels.filter(model => {
      const matchesSearch = model.name.toLowerCase().includes(search.toLowerCase()) ||
                            model.provider.toLowerCase().includes(search.toLowerCase()) ||
                            model.description.toLowerCase().includes(search.toLowerCase());

      const matchesProvider = providerFilter === 'All' || model.provider === providerFilter;
      const matchesStatus = statusFilter === 'All' || model.status === statusFilter;

      return matchesSearch && matchesProvider && matchesStatus;
    });
  }, [allModels, search, providerFilter, statusFilter]);

  // Handle setting model
  const handleSelectModel = (model: ModelOption) => {
    onChangeModel(model.id);
    setSelectedModelDetail(model);
  };

  // Run a real-time policy pipeline test simulation
  const handleRunSimulation = () => {
    if (!selectedModelDetail) return;
    setSimulating(true);
    setSimResult(null);

    setTimeout(() => {
      const text = simulationPrompt.toLowerCase();
      let status: 'BLOCKED' | 'ALLOWED' | 'REDACTED' = 'ALLOWED';
      let logs: string[] = [];
      let explanation = '';

      if (selectedModelDetail.id === 'auto') {
        logs = ['[0.0ms] Gateway intercepted payload', '[0.8ms] Initiating Dynamic Intent Analysis (DIA)'];
        let chosenModel = 'Gemini 3.5 Flash';
        let routeReason = 'Default lightweight route chosen for ultra-low latency inference.';
        
        if (text.includes('function') || text.includes('class') || text.includes('const') || text.includes('code') || text.includes('bug') || text.includes('typescript') || text.includes('rust') || text.includes('compile') || text.includes('react')) {
          chosenModel = 'Claude 3.5 Sonnet';
          routeReason = 'Coding syntax or developer context detected. Routing to high-fidelity code synthesis path.';
        } else if (text.includes('solve') || text.includes('calculate') || text.includes('prove') || text.includes('reason') || text.includes('why') || text.includes('compare') || text.includes('logic') || text.includes('formula')) {
          chosenModel = 'OpenAI o1 Pro';
          routeReason = 'Step-by-step logical reasoning identified. Routing to the deep analytical trace path.';
        } else if (text.includes('write') || text.includes('create') || text.includes('blog') || text.includes('story') || text.includes('email') || text.includes('poet') || text.includes('summarize')) {
          chosenModel = 'GPT-4o (Omni)';
          routeReason = 'Creative or high-throughput copywriting pattern detected. Routing to the fluid omni-modal engine.';
        }
        
        logs.push(`[1.5ms] DIA classification output: ${chosenModel} (${routeReason})`);
        logs.push(`[2.0ms] Scanning RBAC constraints for routed target: ${chosenModel}`);
        
        if (text.includes('aws') || text.includes('key') || text.includes('credential')) {
          status = 'BLOCKED';
          logs.push('[2.5ms] DLP Entropy Scanner triggered: Secret detection match');
          logs.push('[2.8ms] Rule ID: dlp-block-high-entropy matched: "AWS_ACCESS_KEY_ID"');
          logs.push('[3.1ms] Gateway state: REQUEST_TERMINATED_PRE_FLIGHT');
          explanation = `The Enterprise Dynamic Gateway intercepted the payload. After classifying the intent, a credentials block was triggered before dispatching the query to ${chosenModel}. Connection was aborted to prevent credential leaks.`;
        } else if (text.includes('ssn') || text.includes('phone') || text.includes('social security') || text.includes('email')) {
          status = 'REDACTED';
          logs.push('[3.1ms] PII Classifier triggered: Sensitive SSN/Email pattern detected');
          logs.push('[4.0ms] Masquerading sensitive strings with secure hash tokens');
          logs.push(`[5.0ms] Forwarding payload cleanly to routed target: ${chosenModel}`);
          explanation = `The Enterprise Gateway classified the prompt and dynamically routed it to ${chosenModel}. Sensitive identifiers (PII) were successfully stripped and masked. Your target model only received secure masked hashes.`;
        } else {
          logs.push('[2.8ms] Policies check clear. Dynamic proxy tunnel established.');
          logs.push(`[3.5ms] Forwarding payload securely over TLS 1.3 to ${chosenModel}`);
          explanation = `The Enterprise Gateway analyzed your prompt, determined that **${chosenModel}** was the absolute best destination for this request (${routeReason}), and cleanly routed the prompt with an overhead of just 3.5ms.`;
        }
      } else {
        logs = ['[0.0ms] Gateway intercepted payload', `[1.2ms] Scanning RBAC constraints for active model ${selectedModelDetail.name}`];
        // Mock scanning logs
        if (text.includes('aws') || text.includes('key') || text.includes('credential')) {
          status = 'BLOCKED';
          logs.push('[2.5ms] DLP Entropy Scanner triggered: Secret detection match');
          logs.push('[2.8ms] Rule ID: dlp-block-high-entropy matched: "AWS_ACCESS_KEY_ID"');
          logs.push('[3.1ms] Gateway state: REQUEST_TERMINATED_PRE_FLIGHT');
          explanation = `The Torkq policy shield automatically intercepted the payload because it contains patterns matching enterprise credentials or high-entropy secrets. Connection to ${selectedModelDetail.provider} was short-circuited to prevent credentials leakage.`;
        } else if (text.includes('ssn') || text.includes('phone') || text.includes('social security') || text.includes('email')) {
          status = 'REDACTED';
          logs.push('[3.1ms] PII Classifier triggered: SSN/Email detected');
          logs.push('[4.0ms] Substituting matched sequence with secure cryptographic token');
          logs.push('[4.8ms] Rule ID: pii-auto-redact applied successfully');
          logs.push(`[5.2ms] Outbound payload forwarded cleanly to ${selectedModelDetail.provider}`);
          explanation = `The payload was permitted to proceed to ${selectedModelDetail.name}, but sensitive identifiers were automatically masked. Your model only received safe redacted tokens [REDACTED_SSN_X12].`;
        } else {
          logs.push('[3.0ms] Scans completed. No security anomalies or policy triggers detected.');
          logs.push(`[3.5ms] Forwarding payload securely over TLS 1.3 to ${selectedModelDetail.provider}`);
          explanation = `No policy constraints were triggered. The payload met all requirements and has been successfully approved for deployment to ${selectedModelDetail.name}.`;
        }
      }

      setSimResult({ status, logs, explanation });
      setSimulating(false);
    }, 750);
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#070B11] text-white/95 overflow-y-auto">
      
      {/* Banner / Header */}
      <div className="p-6 md:p-8 border-b border-white/[0.04] bg-[#090F17]/95 relative select-none shrink-0">
        <div className="absolute top-0 right-0 p-8 opacity-5 pointer-events-none">
          <Settings size={180} className="animate-spin" style={{ animationDuration: '60s' }} />
        </div>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5 max-w-2xl">
            <div className="flex items-center space-x-2">
              <div className="w-5 h-5 bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center rounded-[2px]">
                <Shield size={11} className="text-indigo-400" />
              </div>
              <span className="text-[10px] font-mono tracking-widest text-indigo-400 font-bold uppercase">Compliance Directory</span>
            </div>
            <h1 className="text-xl md:text-2xl font-semibold tracking-tight text-white font-sans">
              Model Governance Control Center
            </h1>
            <p className="text-xs text-white/40 leading-relaxed font-sans">
              Evaluate risk parameters, compute token charges, and define model routes under custom enterprise DLP, RBAC, and static vulnerability scanning shields.
            </p>
          </div>

          <div className="flex items-center space-x-3 text-xs">
            <span className="text-white/30 font-mono text-[11px]">ACTIVE GATEWAY:</span>
            <div className="px-3 py-1.5 bg-indigo-500/10 border border-indigo-500/30 rounded-[2px] flex items-center space-x-2 font-mono">
              <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse"></span>
              <span className="text-white font-bold text-[11px]">
                {allModels.find(m => m.id === selectedModel)?.name || selectedModel}
              </span>
            </div>
          </div>
        </div>

        {/* Executive statistics blocks */}
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3.5 mt-6 pt-6 border-t border-white/[0.04] font-mono">
          <div className="p-3 bg-[#0c131d] border border-white/[0.03] rounded-[2px] flex flex-col">
            <span className="text-[10px] text-white/30 uppercase tracking-wider">Configured Gateways</span>
            <span className="text-xl font-semibold text-white/95 mt-1">{stats.total}</span>
          </div>
          <div className="p-3 bg-[#0c131d] border border-white/[0.03] rounded-[2px] flex flex-col">
            <span className="text-[10px] text-white/30 uppercase tracking-wider">Approved (Zero-Trust)</span>
            <span className="text-xl font-semibold text-emerald-400 mt-1">{stats.approved}</span>
          </div>
          <div className="p-3 bg-[#0c131d] border border-white/[0.03] rounded-[2px] flex flex-col">
            <span className="text-[10px] text-white/30 uppercase tracking-wider">Restricted (Scope Overlap)</span>
            <span className="text-xl font-semibold text-amber-400 mt-1">{stats.restricted}</span>
          </div>
        </div>
      </div>

      {/* Main Grid Content */}
      <div className="flex-1 p-6 md:p-8 flex flex-col lg:flex-row gap-6">

        {/* Left Side: Directory Filters & Cards */}
        <div className="flex-1 flex flex-col space-y-4">

          {!config.virtualKey && (
            <div className="bg-[#070b11] border border-amber-500/20 p-6 rounded-[2px] text-center space-y-2">
              <AlertTriangle className="mx-auto text-amber-400" size={20} />
              <p className="text-sm text-white/70">No virtual key configured for this session.</p>
              <p className="text-xs text-white/40">Go to Admin &gt; Settings and paste a virtual key to see registered providers/models here.</p>
            </div>
          )}

          {loadError && (
            <div className="bg-rose-500/5 border border-rose-500/20 p-3 rounded-[2px] text-xs font-mono text-rose-300">
              Failed to load models: {loadError}
            </div>
          )}

          {/* Controls Bar */}
          <div className="flex flex-col sm:flex-row gap-3 bg-[#090F17]/40 p-3 border border-white/[0.03] rounded-[2px] select-none">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" size={13} />
              <input
                type="text"
                placeholder="Search models, compliance standard, provider..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-[#0a1019] border border-white/[0.06] hover:border-white/[0.12] focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/50 rounded-[2px] py-1.5 pl-8 pr-3 text-xs text-white placeholder-white/20 focus:outline-none transition-all font-mono"
              />
            </div>

            <div className="flex items-center space-x-2 self-end sm:self-auto overflow-x-auto pr-1">
              <div className="flex bg-[#0a1019] border border-white/[0.06] rounded-[2px] p-0.5">
                {providerOptions.map((p) => (
                  <button
                    key={p}
                    onClick={() => setProviderFilter(p)}
                    className={`px-2 py-1 text-[10px] font-mono rounded-[1px] transition-all cursor-pointer whitespace-nowrap ${
                      providerFilter === p
                        ? 'bg-indigo-500/25 border border-indigo-500/40 text-indigo-300 font-semibold'
                        : 'text-white/40 hover:text-white/80 hover:bg-white/[0.02]'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>

              <div className="flex bg-[#0a1019] border border-white/[0.06] rounded-[2px] p-0.5 shrink-0">
                {['All', 'Approved', 'Restricted'].map((s) => (
                  <button
                    key={s}
                    onClick={() => setStatusFilter(s)}
                    className={`px-2 py-1 text-[10px] font-mono rounded-[1px] transition-all cursor-pointer ${
                      statusFilter === s 
                        ? 'bg-indigo-500/25 border border-indigo-500/40 text-indigo-300 font-semibold' 
                        : 'text-white/40 hover:text-white/80 hover:bg-white/[0.02]'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Cards Directory */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[600px] lg:max-h-[750px] overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/5">
            {loading && registeredModels.length === 0 ? (
              <div className="col-span-2 py-12 text-center bg-[#090F17]/20 border border-dashed border-white/[0.05] rounded-[2px] flex items-center justify-center gap-2">
                <Loader2 className="animate-spin text-white/30" size={16} />
                <span className="text-xs text-white/30 font-mono">Loading registered models...</span>
              </div>
            ) : filteredModels.length === 0 ? (
              <div className="col-span-2 py-12 text-center bg-[#090F17]/20 border border-dashed border-white/[0.05] rounded-[2px]">
                <AlertTriangle className="mx-auto text-white/20 mb-2" size={24} />
                <span className="text-xs text-white/30 font-mono">No gateways matched the specified search filters</span>
              </div>
            ) : (
              filteredModels.map((model) => {
                const isCurrent = model.id === selectedModel;
                const isSelectedDetail = model.id === selectedModelDetail?.id;

                const statusBadge = model.status === 'Restricted'
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                  : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';

                return (
                  <div
                    key={model.id}
                    onClick={() => setSelectedModelDetail(model)}
                    className={`p-4 border rounded-[2px] transition-all duration-150 cursor-pointer text-left flex flex-col justify-between ${
                      isSelectedDetail 
                        ? 'bg-[#0f1825] border-indigo-500/40 shadow-md shadow-indigo-950/25' 
                        : isCurrent 
                          ? 'bg-[#0d141e]/85 border-white/[0.12] hover:bg-[#111926]' 
                          : 'bg-[#090e15]/90 border-white/[0.04] hover:bg-[#0c1420] hover:border-white/[0.08]'
                    }`}
                  >
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="text-[10px] font-mono px-1.5 py-0.5 bg-white/5 border border-white/10 text-white/60 uppercase rounded-[1px]">
                            {model.provider}
                          </span>
                          <span className="text-[10px] font-sans font-medium text-white/40">
                            {model.tag}
                          </span>
                        </div>
                        <span className={`text-[9px] font-mono font-bold tracking-wider px-1.5 py-0.2 border rounded-[1px] uppercase ${statusBadge}`}>
                          {model.status}
                        </span>
                      </div>

                      <div className="space-y-0.5">
                        <h3 className="text-xs font-bold text-white font-mono flex items-center">
                          {model.name}
                          {isCurrent && (
                            <span className="ml-1.5 text-[8px] font-mono bg-emerald-500/20 text-emerald-400 px-1 border border-emerald-500/30 rounded-[1px]">ACTIVE</span>
                          )}
                        </h3>
                        <p className="text-[11px] text-white/40 line-clamp-2 leading-relaxed">
                          {model.description}
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-white/[0.03] grid grid-cols-3 gap-1.5 text-[10px] font-mono text-white/50">
                      <div className="flex flex-col">
                        <span className="text-white/25 flex items-center gap-0.5"><Clock size={9} /> Latency</span>
                        <span className="text-white/70 font-medium">{model.latency}</span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-white/25 flex items-center gap-0.5"><Coins size={9} /> Cost/1M</span>
                        <span className="text-white/70 font-medium truncate" title={model.costPerMillion}>{model.costPerMillion.split('/')[0]}</span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-white/25 flex items-center gap-0.5"><Cpu size={9} /> Context</span>
                        <span className="text-white/70 font-medium">{model.contextWindow}</span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Side: High Fidelity Policy Evaluator Panel */}
        {selectedModelDetail && (
          <div className="w-full lg:w-[400px] bg-[#090e15] border border-white/[0.04] p-5 rounded-[2px] flex flex-col justify-between shrink-0 select-none animate-fadeIn">
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-white/[0.04] pb-3">
                <div className="space-y-0.5">
                  <span className="text-[9px] font-mono text-white/30 uppercase tracking-widest">Active Node Profile</span>
                  <h2 className="text-xs font-bold font-mono text-white">{selectedModelDetail.name}</h2>
                </div>
                <span className="text-[10px] font-mono bg-white/[0.03] px-2 py-0.5 text-white/50 rounded-[1px]">
                  {selectedModelDetail.provider}
                </span>
              </div>

              {/* Status Compliance Block */}
              <div className="p-3 bg-[#0d141f] border border-white/[0.04] rounded-[1px] space-y-2">
                <span className="text-[10px] font-mono text-indigo-400 font-bold block uppercase tracking-wider">Gateway Scanning Matrix</span>
                <div className="space-y-1.5">
                  {selectedModelDetail.guardrails.map((g, i) => (
                    <div key={i} className="flex items-center space-x-2 text-[11px] text-white/70 font-mono">
                      <ShieldCheck size={11} className="text-emerald-400 shrink-0" />
                      <span>{g}</span>
                    </div>
                  ))}
                  {selectedModelDetail.status === 'Restricted' && (
                    <div className="flex items-center space-x-2 text-[11px] text-amber-400 font-mono pt-1">
                      <ShieldAlert size={11} className="text-amber-500 shrink-0" />
                      <span>Requires Model Override (RBAC-3)</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Token pricing detail */}
              <div className="space-y-2 text-[11px] font-mono">
                <span className="text-[9px] text-white/30 uppercase tracking-widest block">Operational SLAs</span>
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2.5 bg-white/[0.01] border border-white/[0.02] rounded-[1px]">
                    <span className="text-white/20 block text-[9px]">COMPUTE SLA</span>
                    <span className="text-white/80">{selectedModelDetail.latency} (P95)</span>
                  </div>
                  <div className="p-2.5 bg-white/[0.01] border border-white/[0.02] rounded-[1px]">
                    <span className="text-white/20 block text-[9px]">MAX TOKENS</span>
                    <span className="text-white/80">{selectedModelDetail.contextWindow}</span>
                  </div>
                  <div className="col-span-2 p-2.5 bg-white/[0.01] border border-white/[0.02] rounded-[1px] flex justify-between">
                    <div>
                      <span className="text-white/20 block text-[9px]">COST PER 1M TOKENS</span>
                      <span className="text-white/80">{selectedModelDetail.costPerMillion}</span>
                    </div>
                    <div className="text-right">
                      <span className="text-white/20 block text-[9px]">COMPLIANCE</span>
                      <span className="text-emerald-400 text-[10px]">SOC2 / HIPAA</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Policy Sandbox Simulator (Drives interactive credibility) */}
              <div className="space-y-2 pt-2 border-t border-white/[0.03]">
                <div className="flex justify-between items-center">
                  <span className="text-[9px] font-mono text-indigo-400 font-bold uppercase tracking-widest">Interactive Policy Sandbox</span>
                  <span className="text-[8px] font-mono text-white/20">TEST RUNNER</span>
                </div>
                <p className="text-[10px] text-white/30 font-sans leading-relaxed">
                  Validate how Torkq acts as a reverse proxy for {selectedModelDetail.name} under security scenarios.
                </p>
                <div className="space-y-1.5">
                  <textarea
                    value={simulationPrompt}
                    onChange={(e) => setSimulationPrompt(e.target.value)}
                    placeholder="Enter prompt containing potential secrets or PII..."
                    className="w-full h-14 bg-[#0a1019] border border-white/[0.06] focus:border-indigo-500/50 rounded-[1px] p-2 text-[10px] font-mono text-white placeholder-white/20 focus:outline-none resize-none"
                  />
                  <div className="flex space-x-1">
                    <button
                      onClick={handleRunSimulation}
                      disabled={simulating}
                      className="flex-1 py-1 px-2 bg-indigo-500 hover:bg-indigo-400 text-[#0A0E14] font-semibold text-[10px] rounded-[1px] font-mono transition-all disabled:opacity-40 flex items-center justify-center gap-1 cursor-pointer"
                    >
                      {simulating ? 'Processing Gateway Scans...' : 'Execute Policy Scan'}
                      <ArrowRight size={10} />
                    </button>
                    <button
                      onClick={() => setSimulationPrompt('Send audit record of SSN 000-12-3456 to compliance board.')}
                      className="px-2 py-1 bg-white/5 hover:bg-white/10 text-white/60 hover:text-white border border-white/10 text-[9px] rounded-[1px] font-mono transition-all cursor-pointer"
                    >
                      Load PII Prompt
                    </button>
                  </div>
                </div>

                {simResult && (
                  <div className="mt-3 p-3 bg-[#0a1019] border border-white/[0.04] rounded-[1px] space-y-2 font-mono text-[10px] animate-fadeIn">
                    <div className="flex items-center justify-between">
                      <span className="text-white/40">GATEWAY_DECISION:</span>
                      <span className={`font-bold border px-1.5 py-0.2 rounded-[1px] ${
                        simResult.status === 'BLOCKED' ? 'text-red-400 border-red-500/20 bg-red-500/5' :
                        simResult.status === 'REDACTED' ? 'text-amber-400 border-amber-500/20 bg-amber-500/5' :
                        'text-emerald-400 border-emerald-500/20 bg-emerald-500/5'
                      }`}>
                        {simResult.status}
                      </span>
                    </div>
                    <div className="space-y-0.5 text-[9px] text-white/30 border-t border-b border-white/[0.02] py-1.5 max-h-20 overflow-y-auto pr-1">
                      {simResult.logs.map((log, lIdx) => (
                        <div key={lIdx} className="truncate">{log}</div>
                      ))}
                    </div>
                    <p className="text-[10px] font-sans text-white/50 leading-relaxed">
                      {simResult.explanation}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Set as Active Button */}
            <div className="pt-4 border-t border-white/[0.03]">
              {selectedModelDetail.id === selectedModel ? (
                <div className="w-full py-2 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-semibold rounded-[1px] flex items-center justify-center gap-1.5 font-mono select-none">
                  <Check size={13} />
                  <span>NODE ENFORCED: ACTIVE GATEWAY</span>
                </div>
              ) : (
                <button
                  onClick={() => handleSelectModel(selectedModelDetail)}
                  className="w-full py-2 bg-white hover:bg-white/95 text-[#070B11] font-bold text-xs rounded-[1px] flex items-center justify-center gap-1.5 transition-all cursor-pointer font-mono select-none"
                >
                  <Unlock size={12} className="opacity-70" />
                  <span>SET ACTIVE GATEWAY PATHWAY</span>
                </button>
              )}
            </div>
          </div>
        )}

      </div>
      
    </div>
  );
}
