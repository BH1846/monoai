import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, Copy, KeyRound, Loader2, Plus, Trash2 } from 'lucide-react';
import { ModelRecord, VirtualKeyRecord } from '../../types';
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
                <td className="py-3 px-4 font-mono text-[10px] text-white/50">{k.team_id || '—'}</td>
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
                <td className="py-3 px-4 text-right">
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
