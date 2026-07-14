import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ArrowLeft, Check, Copy, Eye, KeyRound, Loader2, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { ModelRecord, UserPromptTransaction, VirtualKeyRecord } from '../../types';
import { useGateway } from '../../context/GatewayContext';

interface UsersTabProps {
  showToast: (msg: string) => void;
}

// NOTE: the original mock UsersTab modeled `UserRecord` (name/email/role/
// lastActive/inputTokens/outputTokens) -- none of that exists on the
// gateway's virtual-key model (auth/models.py::VirtualKey). This rewrite
// backs entirely onto /v1/admin/keys, so those fields are simply dropped
// rather than fabricated. What we do have: key_id, team_id, policy_id,
// model_allowlist, budget_usd_monthly/spent, rate limits, and active state.
export default function UsersTab({ showToast }: UsersTabProps) {
  const { config, adminFetch } = useGateway();

  const [keys, setKeys] = useState<VirtualKeyRecord[]>([]);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [teamId, setTeamId] = useState('');
  const [policyId, setPolicyId] = useState('default');
  const [allowlist, setAllowlist] = useState<string[]>([]);
  const [budgetUsd, setBudgetUsd] = useState('');
  const [rateLimitRps, setRateLimitRps] = useState('5');
  const [creating, setCreating] = useState(false);
  const [justCreatedKey, setJustCreatedKey] = useState<{ key: string; key_id: string } | null>(null);
  const [copied, setCopied] = useState(false);

  // Per-user prompt/reply drill-down (real data from GET /v1/admin/transactions)
  const [inspectKey, setInspectKey] = useState<VirtualKeyRecord | null>(null);
  const [openSession, setOpenSession] = useState<string | null>(null);
  const [txns, setTxns] = useState<UserPromptTransaction[]>([]);
  const [txnsLoading, setTxnsLoading] = useState(false);
  const [txnsError, setTxnsError] = useState<string | null>(null);

  const loadTransactions = useCallback(async (key: VirtualKeyRecord) => {
    setTxnsLoading(true);
    setTxnsError(null);
    try {
      const res = await adminFetch(`transactions?virtual_key_id=${encodeURIComponent(key.key_id)}&limit=200`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      setTxns(data.transactions || []);
    } catch (err: any) {
      setTxnsError(err.message || 'Failed to load prompt history');
      setTxns([]);
    } finally {
      setTxnsLoading(false);
    }
  }, [adminFetch]);

  const openInspect = (key: VirtualKeyRecord) => {
    setInspectKey(key);
    setOpenSession(null);
    loadTransactions(key);
  };

  const loadAll = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [kRes, mRes] = await Promise.all([adminFetch('keys'), adminFetch('models')]);
      if (!kRes.ok || !mRes.ok) {
        const failed = !kRes.ok ? kRes : mRes;
        const body = await failed.json().catch(() => ({}));
        throw new Error(body?.error?.message || body?.detail || `HTTP ${failed.status}`);
      }
      const kData = await kRes.json();
      const mData = await mRes.json();
      setKeys(kData.keys || []);
      setModels(mData.models || []);
    } catch (err: any) {
      setLoadError(err.message || 'Failed to load keys/models from the gateway');
    } finally {
      setLoading(false);
    }
  }, [adminFetch]);

  useEffect(() => {
    if (config.adminKey) {
      loadAll();
    }
  }, [config.adminKey, loadAll]);

  const toggleAllowlistModel = (modelId: string) => {
    setAllowlist((prev) => (prev.includes(modelId) ? prev.filter((m) => m !== modelId) : [...prev, modelId]));
  };

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setJustCreatedKey(null);
    try {
      const res = await adminFetch('keys', {
        method: 'POST',
        body: JSON.stringify({
          team_id: teamId.trim() || undefined,
          policy_id: policyId.trim() || 'default',
          model_allowlist: allowlist.length > 0 ? allowlist : undefined,
          budget_usd_monthly: budgetUsd.trim() ? parseFloat(budgetUsd) : undefined,
          rate_limit_rps: rateLimitRps.trim() ? parseFloat(rateLimitRps) : undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      setJustCreatedKey({ key: data.key, key_id: data.key_id });
      setTeamId('');
      setPolicyId('default');
      setAllowlist([]);
      setBudgetUsd('');
      setRateLimitRps('5');
      showToast(`Virtual key ${data.key_id} created`);
      await loadAll();
    } catch (err: any) {
      showToast(`Failed to create key: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (keyId: string) => {
    if (!window.confirm(`Revoke key ${keyId}? This cannot be undone.`)) return;
    try {
      const res = await adminFetch(`keys/${keyId}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      }
      showToast(`Key ${keyId} revoked`);
      await loadAll();
    } catch (err: any) {
      showToast(`Failed to revoke key: ${err.message}`);
    }
  };

  const copyKey = async () => {
    if (!justCreatedKey) return;
    try {
      await navigator.clipboard.writeText(justCreatedKey.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      showToast('Clipboard copy failed -- select and copy the key manually');
    }
  };

  if (!config.adminKey) {
    return (
      <div className="bg-[#070b11] border border-amber-500/20 p-8 rounded-[2px] text-center space-y-2">
        <AlertTriangle className="mx-auto text-amber-400" size={22} />
        <p className="text-sm text-white/70">No admin key configured for this session.</p>
        <p className="text-xs text-white/40">Go to Settings and paste your gateway's admin key to manage virtual keys.</p>
      </div>
    );
  }

  // ---- Per-user prompt inspection view (grouped by chat session) ----
  if (inspectKey) {
    const statusStyle = (s: string) =>
      s === 'blocked' ? 'text-rose-400 border-rose-500/20 bg-rose-500/5'
      : s === 'redacted' ? 'text-amber-400 border-amber-500/20 bg-amber-500/5'
      : 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5';

    // Group this user's requests into chat sessions. Each session = one chat
    // window (session_id); turns within it are ordered oldest -> newest.
    const sessionMap = new Map<string, UserPromptTransaction[]>();
    for (const t of txns) {
      const sid = t.session_id || t.id;
      const arr = sessionMap.get(sid);
      if (arr) arr.push(t);
      else sessionMap.set(sid, [t]);
    }
    const sessions = Array.from(sessionMap.entries()).map(([sid, turns]) => {
      const ordered = [...turns].sort((a, b) => a.timestamp - b.timestamp);
      return {
        sid,
        turns: ordered,
        title: ordered[0]?.originalPrompt?.split('\n')[0]?.slice(0, 80) || '(empty prompt)',
        lastActivity: Math.max(...turns.map((t) => t.timestamp)),
        blocked: turns.filter((t) => t.status === 'blocked').length,
        redacted: turns.filter((t) => t.status === 'redacted').length,
      };
    }).sort((a, b) => b.lastActivity - a.lastActivity);

    const activeSession = openSession ? sessions.find((s) => s.sid === openSession) : null;

    const header = (
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <button
            onClick={() => (activeSession ? setOpenSession(null) : setInspectKey(null))}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-[1px] text-[11px] font-mono text-white/70 transition-colors cursor-pointer"
          >
            <ArrowLeft size={12} />
            <span>{activeSession ? 'BACK TO SESSIONS' : 'BACK TO USERS'}</span>
          </button>
          <div className="text-xs font-mono text-white/80">
            <span className="text-indigo-300">{inspectKey.team_id || inspectKey.key_id}</span>
            <span className="text-white/30 ml-2">
              {activeSession ? `session ${activeSession.sid.slice(0, 18)}` : 'chat sessions'}
            </span>
          </div>
        </div>
        <button
          onClick={() => loadTransactions(inspectKey)}
          disabled={txnsLoading}
          className="flex items-center space-x-1.5 text-[10px] font-mono text-white/50 hover:text-white/80 transition-colors cursor-pointer disabled:opacity-40"
        >
          <RefreshCw size={11} className={txnsLoading ? 'animate-spin' : ''} />
          <span>Refresh</span>
        </button>
      </div>
    );

    if (txnsLoading && txns.length === 0) {
      return (
        <div className="space-y-4">
          {header}
          <div className="py-12 text-center text-white/30 font-mono text-xs flex items-center justify-center gap-2">
            <Loader2 size={14} className="animate-spin" /> Loading prompt history...
          </div>
        </div>
      );
    }

    if (txns.length === 0) {
      return (
        <div className="space-y-4">
          {header}
          {txnsError && (
            <div className="bg-rose-500/5 border border-rose-500/20 p-3 rounded-[2px] text-xs font-mono text-rose-300">{txnsError}</div>
          )}
          <div className="py-12 text-center bg-[#070b11] border border-dashed border-white/[0.06] rounded-[2px] text-white/30 font-mono text-xs">
            No requests recorded for this user yet. Prompts appear here after they send a chat message.
          </div>
        </div>
      );
    }

    // ---- Level 2: one session's conversation ----
    if (activeSession) {
      return (
        <div className="space-y-4">
          {header}
          <div className="space-y-3">
            {activeSession.turns.map((t) => (
              <div key={t.id} className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-hidden">
                <div className="px-3 py-2 border-b border-white/[0.06] bg-white/[0.01] flex flex-wrap items-center justify-between gap-2 font-mono text-[9px]">
                  <div className="flex items-center gap-3">
                    <span className={`px-2 py-0.5 border rounded-[1px] font-bold tracking-wider text-[9px] ${statusStyle(t.status)}`}>
                      {t.status.toUpperCase()}
                    </span>
                    <span className="text-white/40">{new Date(t.timestamp * 1000).toLocaleString()}</span>
                    <span className="text-white/60">{t.model || 'auto'}</span>
                  </div>
                  <div className="flex items-center gap-3 text-white/40">
                    <span>in {t.inputTokens} / out {t.outputTokens} tok</span>
                    {t.cost != null && <span>${t.cost.toFixed(6)}</span>}
                  </div>
                </div>

                <div className="p-3 space-y-3">
                  {/* User turn */}
                  <div className="space-y-1">
                    <div className="text-[8px] font-mono text-indigo-300/70 uppercase tracking-widest">User prompt</div>
                    <div className="text-[12px] text-white/85 whitespace-pre-wrap break-words leading-relaxed">{t.originalPrompt || '—'}</div>
                    {t.redactionRulesTriggered.length > 0 && (
                      <div className="mt-1.5 space-y-1 border-l-2 border-amber-500/30 pl-2">
                        <div className="flex flex-wrap gap-1 items-center">
                          <span className="text-[8px] font-mono text-amber-400/80 uppercase tracking-widest mr-1">
                            {t.status === 'blocked' ? 'Blocked on' : 'Redacted before sending'}
                          </span>
                          {t.redactionRulesTriggered.map((r) => (
                            <span key={r} className="text-[8px] font-mono px-1 py-0.2 bg-amber-500/10 border border-amber-500/20 text-amber-300 rounded-[1px]">{r}</span>
                          ))}
                        </div>
                        {t.status !== 'blocked' && t.redactedPrompt && (
                          <div className="text-[11px] font-mono text-amber-200/70 whitespace-pre-wrap break-words leading-relaxed">
                            {t.redactedPrompt}
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Model reply pipeline: raw LLM output -> rehydrated client view */}
                  {t.status === 'blocked' ? (
                    <div className="space-y-1">
                      <div className="text-[8px] font-mono text-emerald-300/70 uppercase tracking-widest">Assistant reply</div>
                      <div className="text-[12px] leading-relaxed">
                        <span className="text-rose-300/70 italic">Blocked at the gateway — never reached a model.</span>
                      </div>
                    </div>
                  ) : t.llmReply && t.llmReply !== t.rehydratedReply ? (
                    <>
                      <div className="space-y-1">
                        <div className="text-[8px] font-mono text-white/40 uppercase tracking-widest">LLM reply (raw — tokens not yet restored)</div>
                        <div className="text-[12px] text-white/55 whitespace-pre-wrap break-words leading-relaxed">{t.llmReply}</div>
                      </div>
                      <div className="space-y-1 border-l-2 border-emerald-500/30 pl-2">
                        <div className="text-[8px] font-mono text-emerald-300/70 uppercase tracking-widest">Rehydrated — client view</div>
                        <div className="text-[12px] text-white/85 whitespace-pre-wrap break-words leading-relaxed">{t.rehydratedReply || '—'}</div>
                      </div>
                    </>
                  ) : (
                    <div className="space-y-1">
                      <div className="text-[8px] font-mono text-emerald-300/70 uppercase tracking-widest">Assistant reply</div>
                      <div className="text-[12px] text-white/85 whitespace-pre-wrap break-words leading-relaxed">{t.rehydratedReply || '—'}</div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      );
    }

    // ---- Level 1: list of chat sessions ----
    return (
      <div className="space-y-4">
        {header}
        {txnsError && (
          <div className="bg-rose-500/5 border border-rose-500/20 p-3 rounded-[2px] text-xs font-mono text-rose-300">{txnsError}</div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {sessions.map((s) => (
            <button
              key={s.sid}
              onClick={() => setOpenSession(s.sid)}
              className="text-left bg-[#070b11] border border-white/[0.08] hover:border-indigo-500/40 hover:bg-[#0b1119] rounded-[2px] p-4 transition-all cursor-pointer space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-[9px] font-mono text-white/30 uppercase tracking-widest">Chat session</span>
                <span className="text-[9px] font-mono text-white/40">{new Date(s.lastActivity * 1000).toLocaleString()}</span>
              </div>
              <div className="text-[13px] text-white/90 font-medium truncate">{s.title}</div>
              <div className="flex items-center gap-2 font-mono text-[9px]">
                <span className="px-1.5 py-0.5 bg-white/5 border border-white/10 text-white/60 rounded-[1px]">{s.turns.length} msg{s.turns.length !== 1 ? 's' : ''}</span>
                {s.blocked > 0 && <span className="px-1.5 py-0.5 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-[1px]">{s.blocked} blocked</span>}
                {s.redacted > 0 && <span className="px-1.5 py-0.5 bg-amber-500/10 border border-amber-500/20 text-amber-300 rounded-[1px]">{s.redacted} redacted</span>}
                {s.blocked === 0 && s.redacted === 0 && <span className="px-1.5 py-0.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-[1px]">clean</span>}
              </div>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">

      {loadError && (
        <div className="bg-rose-500/5 border border-rose-500/20 p-3 rounded-[2px] text-xs font-mono text-rose-300">
          Failed to load: {loadError}
        </div>
      )}

      {/* CREATE USER/KEY */}
      <div className="bg-[#070c14] border border-white/[0.08] p-5 rounded-[2px] space-y-4">
        <div className="flex items-center space-x-2">
          <KeyRound size={16} className="text-rose-400" />
          <span className="text-xs font-mono font-bold uppercase text-white/90">Create User / Virtual Key</span>
        </div>

        <form onSubmit={handleCreateKey} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-white/45 uppercase block">User Name / Email</label>
              <input
                type="text"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                placeholder="alice@company.com"
                className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-white/45 uppercase block">Policy ID</label>
              <input
                type="text"
                value={policyId}
                onChange={(e) => setPolicyId(e.target.value)}
                placeholder="default"
                className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-white/45 uppercase block">Monthly Budget (USD)</label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={budgetUsd}
                onChange={(e) => setBudgetUsd(e.target.value)}
                placeholder="unlimited"
                className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-mono text-white/45 uppercase block">Rate Limit (RPS)</label>
              <input
                type="number"
                min="0"
                step="0.1"
                value={rateLimitRps}
                onChange={(e) => setRateLimitRps(e.target.value)}
                className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[10px] font-mono text-white/45 uppercase block">
              Model Allowlist <span className="text-white/25 normal-case">(none selected = all models allowed, including Auto-Routing)</span>
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => toggleAllowlistModel('auto')}
                className={`text-[10px] font-mono px-2 py-1 rounded-[1px] border transition-colors cursor-pointer ${
                  allowlist.includes('auto')
                    ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300'
                    : 'bg-white/[0.02] border-white/10 text-white/50 hover:border-white/20'
                }`}
                title="Dynamic difficulty-tier auto-routing"
              >
                {allowlist.includes('auto') && <Check size={9} className="inline mr-1 -mt-0.5" />}
                auto
              </button>
              {models.map((m) => (
                <button
                  type="button"
                  key={m.model_id}
                  onClick={() => toggleAllowlistModel(m.model_id)}
                  className={`text-[10px] font-mono px-2 py-1 rounded-[1px] border transition-colors cursor-pointer ${
                    allowlist.includes(m.model_id)
                      ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300'
                      : 'bg-white/[0.02] border-white/10 text-white/50 hover:border-white/20'
                  }`}
                >
                  {allowlist.includes(m.model_id) && <Check size={9} className="inline mr-1 -mt-0.5" />}
                  {m.model_id}
                </button>
              ))}
            </div>
            {models.length === 0 && (
              <div className="text-[11px] text-white/30 font-mono">No registered models yet -- add some in the Providers tab to allow specific ones (auto-routing is always available above).</div>
            )}
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={creating}
              className="flex items-center space-x-1.5 px-4 py-2 bg-rose-500/10 border border-rose-500/30 text-rose-300 rounded-[1px] font-mono text-xs hover:bg-rose-500/15 transition-colors cursor-pointer disabled:opacity-50"
            >
              {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
              <span>CREATE KEY</span>
            </button>
          </div>
        </form>

        {justCreatedKey && (
          <div className="bg-amber-500/5 border border-amber-500/30 p-4 rounded-[2px] space-y-2 animate-fadeIn">
            <div className="flex items-center space-x-2 text-amber-400 text-xs font-mono font-bold">
              <AlertTriangle size={13} />
              <span>SHOWN ONLY ONCE — copy this key now, it cannot be retrieved again</span>
            </div>
            <div className="flex items-center space-x-2">
              <code className="flex-1 bg-black/40 border border-white/10 rounded-[1px] px-3 py-2 text-xs font-mono text-white/90 break-all select-all">
                {justCreatedKey.key}
              </code>
              <button
                onClick={copyKey}
                className="shrink-0 px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-[1px] text-white/70 transition-colors cursor-pointer"
                title="Copy to clipboard"
              >
                {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
              </button>
            </div>
            <div className="text-[10px] font-mono text-white/40">key_id: {justCreatedKey.key_id}</div>
          </div>
        )}
      </div>

      {/* KEYS LIST */}
      <div className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[900px]">
          <thead>
            <tr className="border-b border-white/[0.08] bg-white/[0.02] text-white/40 font-mono text-[9px] uppercase tracking-wider">
              <th className="py-2.5 px-4">Key ID</th>
              <th className="py-2.5 px-4">User</th>
              <th className="py-2.5 px-4">Policy</th>
              <th className="py-2.5 px-4">Model Allowlist</th>
              <th className="py-2.5 px-4">Budget (spent / limit)</th>
              <th className="py-2.5 px-4">Active</th>
              <th className="py-2.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {loading && keys.length === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-xs text-white/30 font-mono">Loading keys...</td></tr>
            )}
            {!loading && keys.length === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-xs text-white/30 font-mono">No virtual keys created yet.</td></tr>
            )}
            {keys.map((k) => (
              <tr key={k.key_id} className="hover:bg-white/[0.01] transition-colors">
                <td className="py-3 px-4 font-mono text-[10px] text-white/80">{k.key_id}</td>
                <td className="py-3 px-4 font-mono text-[10px]">
                  <button
                    onClick={() => openInspect(k)}
                    className="text-white/60 hover:text-indigo-300 hover:underline transition-colors cursor-pointer"
                    title="View this user's prompt history"
                  >
                    {k.team_id || '—'}
                  </button>
                </td>
                <td className="py-3 px-4 font-mono text-[10px] text-indigo-300">{k.policy_id}</td>
                <td className="py-3 px-4 font-mono text-[10px] text-white/50">
                  {k.model_allowlist && k.model_allowlist.length > 0 ? k.model_allowlist.join(', ') : 'all models'}
                </td>
                <td className="py-3 px-4 font-mono text-[10px] text-white/50">
                  ${k.budget_usd_spent.toFixed(2)} / {k.budget_usd_monthly != null ? `$${k.budget_usd_monthly.toFixed(2)}` : 'unlimited'}
                </td>
                <td className="py-3 px-4">
                  <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded-[1px] border ${k.active ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-white/5 border-white/5 text-white/35'}`}>
                    {k.active ? 'ACTIVE' : 'REVOKED'}
                  </span>
                </td>
                <td className="py-3 px-4 text-right whitespace-nowrap">
                  <button
                    onClick={() => openInspect(k)}
                    className="text-[10px] font-mono px-2 py-0.5 rounded-[1px] border border-indigo-500/20 bg-indigo-500/5 hover:bg-indigo-500/10 text-indigo-300 transition-colors inline-flex items-center space-x-1 cursor-pointer mr-2"
                    title="View this user's prompt history"
                  >
                    <Eye size={10} />
                    <span>PROMPTS</span>
                  </button>
                  <button
                    onClick={() => handleRevoke(k.key_id)}
                    disabled={!k.active}
                    className="text-[10px] font-mono px-2 py-0.5 rounded-[1px] border border-rose-500/20 bg-rose-500/5 hover:bg-rose-500/10 text-rose-300 transition-colors inline-flex items-center space-x-1 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <Trash2 size={10} />
                    <span>REVOKE</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

    </div>
  );
}
