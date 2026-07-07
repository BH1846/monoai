import React, { useCallback, useEffect, useState } from 'react';
import { Server, Cpu, Plus, Trash2, Loader2, KeyRound, AlertTriangle } from 'lucide-react';
import { ProviderRecord, ModelRecord } from '../../types';
import { useGateway } from '../../context/GatewayContext';

interface ProvidersTabProps {
  showToast: (msg: string) => void;
}

export default function ProvidersTab({ showToast }: ProvidersTabProps) {
  const { config, adminFetch } = useGateway();

  const [providers, setProviders] = useState<ProviderRecord[]>([]);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [providerName, setProviderName] = useState('');
  const [providerKind, setProviderKind] = useState<'openai-compatible' | 'ollama'>('openai-compatible');
  const [providerBaseUrl, setProviderBaseUrl] = useState('');
  const [providerApiKey, setProviderApiKey] = useState('');
  const [creatingProvider, setCreatingProvider] = useState(false);
  const [lastCreatedKeyLast4, setLastCreatedKeyLast4] = useState<string | null>(null);

  const [modelId, setModelId] = useState('');
  const [modelProviderId, setModelProviderId] = useState('');
  const [modelUpstream, setModelUpstream] = useState('');
  const [modelDisplayName, setModelDisplayName] = useState('');
  const [creatingModel, setCreatingModel] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [pRes, mRes] = await Promise.all([adminFetch('providers'), adminFetch('models')]);
      if (!pRes.ok || !mRes.ok) {
        const failed = !pRes.ok ? pRes : mRes;
        const body = await failed.json().catch(() => ({}));
        throw new Error(body?.error?.message || body?.detail || `HTTP ${failed.status}`);
      }
      const pData = await pRes.json();
      const mData = await mRes.json();
      setProviders(pData.providers || []);
      setModels(mData.models || []);
    } catch (err: any) {
      setLoadError(err.message || 'Failed to load providers/models from the gateway');
    } finally {
      setLoading(false);
    }
  }, [adminFetch]);

  useEffect(() => {
    if (config.adminKey) {
      loadAll();
    }
  }, [config.adminKey, loadAll]);

  const handleCreateProvider = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!providerName.trim() || !providerBaseUrl.trim()) {
      showToast('Provider name and base URL are required');
      return;
    }
    setCreatingProvider(true);
    setLastCreatedKeyLast4(null);
    try {
      const res = await adminFetch('providers', {
        method: 'POST',
        body: JSON.stringify({
          name: providerName.trim(),
          kind: providerKind,
          base_url: providerBaseUrl.trim(),
          api_key: providerApiKey.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      setLastCreatedKeyLast4(data.key_last4 || null);
      setProviderName('');
      setProviderBaseUrl('');
      setProviderApiKey('');
      showToast(`Provider "${data.name}" registered`);
      await loadAll();
    } catch (err: any) {
      showToast(`Failed to create provider: ${err.message}`);
    } finally {
      setCreatingProvider(false);
    }
  };

  const handleDeleteProvider = async (providerId: string) => {
    if (!window.confirm('Delete this provider? Models registered against it may become unreachable.')) return;
    try {
      const res = await adminFetch(`providers/${providerId}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      }
      showToast('Provider deleted');
      await loadAll();
    } catch (err: any) {
      showToast(`Failed to delete provider: ${err.message}`);
    }
  };

  const handleCreateModel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!modelId.trim() || !modelProviderId) {
      showToast('Model ID and provider are required');
      return;
    }
    setCreatingModel(true);
    try {
      const res = await adminFetch('models', {
        method: 'POST',
        body: JSON.stringify({
          model_id: modelId.trim(),
          provider_id: modelProviderId,
          upstream_model: modelUpstream.trim() || undefined,
          display_name: modelDisplayName.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      setModelId('');
      setModelUpstream('');
      setModelDisplayName('');
      showToast(`Model "${data.model_id}" registered`);
      await loadAll();
    } catch (err: any) {
      showToast(`Failed to create model: ${err.message}`);
    } finally {
      setCreatingModel(false);
    }
  };

  const handleDeleteModel = async (modelIdToDelete: string) => {
    if (!window.confirm('Delete this model registration?')) return;
    try {
      const res = await adminFetch(`models/${modelIdToDelete}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
      }
      showToast('Model deleted');
      await loadAll();
    } catch (err: any) {
      showToast(`Failed to delete model: ${err.message}`);
    }
  };

  if (!config.adminKey) {
    return (
      <div className="bg-[#070b11] border border-amber-500/20 p-8 rounded-[2px] text-center space-y-2">
        <AlertTriangle className="mx-auto text-amber-400" size={22} />
        <p className="text-sm text-white/70">No admin key configured for this session.</p>
        <p className="text-xs text-white/40">Go to Settings and paste your gateway's admin key to manage providers and models.</p>
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

      {/* ADD PROVIDER */}
      <div className="bg-[#070c14] border border-white/[0.08] p-5 rounded-[2px] space-y-4">
        <div className="flex items-center space-x-2">
          <Server size={16} className="text-rose-400" />
          <span className="text-xs font-mono font-bold uppercase text-white/90">Add Provider</span>
        </div>
        <form onSubmit={handleCreateProvider} className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Name</label>
            <input
              type="text"
              value={providerName}
              onChange={(e) => setProviderName(e.target.value)}
              placeholder="my-openai"
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Kind</label>
            <select
              value={providerKind}
              onChange={(e) => setProviderKind(e.target.value as 'openai-compatible' | 'ollama')}
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none cursor-pointer"
            >
              <option value="openai-compatible">openai-compatible</option>
              <option value="ollama">ollama</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Base URL</label>
            <input
              type="text"
              value={providerBaseUrl}
              onChange={(e) => setProviderBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">API Key</label>
            <input
              type="password"
              value={providerApiKey}
              onChange={(e) => setProviderApiKey(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
            />
          </div>
          <div className="md:col-span-4 flex items-center justify-between pt-1">
            {lastCreatedKeyLast4 ? (
              <span className="text-[10px] font-mono text-emerald-400 flex items-center gap-1.5">
                <KeyRound size={11} /> Stored — key ends in <strong>...{lastCreatedKeyLast4}</strong> (full key is never shown again)
              </span>
            ) : <span />}
            <button
              type="submit"
              disabled={creatingProvider}
              className="flex items-center space-x-1.5 px-4 py-2 bg-rose-500/10 border border-rose-500/30 text-rose-300 rounded-[1px] font-mono text-xs hover:bg-rose-500/15 transition-colors cursor-pointer disabled:opacity-50"
            >
              {creatingProvider ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
              <span>ADD PROVIDER</span>
            </button>
          </div>
        </form>
      </div>

      {/* PROVIDERS LIST */}
      <div className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[700px]">
          <thead>
            <tr className="border-b border-white/[0.08] bg-white/[0.02] text-white/40 font-mono text-[9px] uppercase tracking-wider">
              <th className="py-2.5 px-4">Name</th>
              <th className="py-2.5 px-4">Kind</th>
              <th className="py-2.5 px-4">Base URL</th>
              <th className="py-2.5 px-4">Key</th>
              <th className="py-2.5 px-4">Status</th>
              <th className="py-2.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {loading && providers.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-xs text-white/30 font-mono">Loading providers...</td></tr>
            )}
            {!loading && providers.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-xs text-white/30 font-mono">No providers registered yet.</td></tr>
            )}
            {providers.map((p) => (
              <tr key={p.provider_id} className="hover:bg-white/[0.01] transition-colors">
                <td className="py-3 px-4 text-xs font-semibold text-white">{p.name}</td>
                <td className="py-3 px-4 font-mono text-[10px] text-white/50">{p.kind}</td>
                <td className="py-3 px-4 font-mono text-[10px] text-white/50">{p.base_url}</td>
                <td className="py-3 px-4 font-mono text-[10px] text-white/50">{p.key_last4 ? `...${p.key_last4}` : '—'}</td>
                <td className="py-3 px-4">
                  <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded-[1px] border ${p.enabled ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-white/5 border-white/5 text-white/35'}`}>
                    {p.enabled ? 'ENABLED' : 'DISABLED'}
                  </span>
                </td>
                <td className="py-3 px-4 text-right">
                  <button
                    onClick={() => handleDeleteProvider(p.provider_id)}
                    className="text-[10px] font-mono px-2 py-0.5 rounded-[1px] border border-rose-500/20 bg-rose-500/5 hover:bg-rose-500/10 text-rose-300 transition-colors inline-flex items-center space-x-1 cursor-pointer"
                  >
                    <Trash2 size={10} />
                    <span>DELETE</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ADD MODEL */}
      <div className="bg-[#070c14] border border-white/[0.08] p-5 rounded-[2px] space-y-4">
        <div className="flex items-center space-x-2">
          <Cpu size={16} className="text-indigo-400" />
          <span className="text-xs font-mono font-bold uppercase text-white/90">Add Model</span>
        </div>
        <form onSubmit={handleCreateModel} className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Model ID</label>
            <input
              type="text"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              placeholder="gpt-4o"
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-indigo-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Provider</label>
            <select
              value={modelProviderId}
              onChange={(e) => setModelProviderId(e.target.value)}
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-indigo-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none cursor-pointer"
            >
              <option value="">Select provider...</option>
              {providers.map((p) => (
                <option key={p.provider_id} value={p.provider_id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Upstream Model</label>
            <input
              type="text"
              value={modelUpstream}
              onChange={(e) => setModelUpstream(e.target.value)}
              placeholder="gpt-4o-2024-08-06"
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-indigo-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Display Name</label>
            <input
              type="text"
              value={modelDisplayName}
              onChange={(e) => setModelDisplayName(e.target.value)}
              placeholder="GPT-4o"
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-indigo-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none"
            />
          </div>
          <div className="md:col-span-4 flex justify-end pt-1">
            <button
              type="submit"
              disabled={creatingModel || providers.length === 0}
              className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 rounded-[1px] font-mono text-xs hover:bg-indigo-500/15 transition-colors cursor-pointer disabled:opacity-50"
              title={providers.length === 0 ? 'Add a provider first' : undefined}
            >
              {creatingModel ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
              <span>ADD MODEL</span>
            </button>
          </div>
        </form>
      </div>

      {/* MODELS LIST */}
      <div className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[700px]">
          <thead>
            <tr className="border-b border-white/[0.08] bg-white/[0.02] text-white/40 font-mono text-[9px] uppercase tracking-wider">
              <th className="py-2.5 px-4">Model ID</th>
              <th className="py-2.5 px-4">Provider</th>
              <th className="py-2.5 px-4">Upstream Model</th>
              <th className="py-2.5 px-4">Display Name</th>
              <th className="py-2.5 px-4">Status</th>
              <th className="py-2.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {loading && models.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-xs text-white/30 font-mono">Loading models...</td></tr>
            )}
            {!loading && models.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-xs text-white/30 font-mono">No models registered yet.</td></tr>
            )}
            {models.map((m) => (
              <tr key={m.model_id} className="hover:bg-white/[0.01] transition-colors">
                <td className="py-3 px-4 text-xs font-semibold text-white font-mono">{m.model_id}</td>
                <td className="py-3 px-4 font-mono text-[10px] text-white/50">{m.provider_name}</td>
                <td className="py-3 px-4 font-mono text-[10px] text-white/50">{m.upstream_model}</td>
                <td className="py-3 px-4 font-mono text-[10px] text-white/50">{m.display_name || '—'}</td>
                <td className="py-3 px-4">
                  <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded-[1px] border ${m.enabled ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-white/5 border-white/5 text-white/35'}`}>
                    {m.enabled ? 'ENABLED' : 'DISABLED'}
                  </span>
                </td>
                <td className="py-3 px-4 text-right">
                  <button
                    onClick={() => handleDeleteModel(m.model_id)}
                    className="text-[10px] font-mono px-2 py-0.5 rounded-[1px] border border-rose-500/20 bg-rose-500/5 hover:bg-rose-500/10 text-rose-300 transition-colors inline-flex items-center space-x-1 cursor-pointer"
                  >
                    <Trash2 size={10} />
                    <span>DELETE</span>
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
