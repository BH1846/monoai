import React, { useState } from 'react';
import { Settings as SettingsIcon, Save, Database, Plug, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { useGateway } from '../../context/GatewayContext';

interface SettingsTabProps {
  rateLimit: string;
  setRateLimit: (val: string) => void;
  enforceStrictSsl: boolean;
  setEnforceStrictSsl: (val: boolean) => void;
  sessionTimeout: string;
  setSessionTimeout: (val: string) => void;
  showToast: (msg: string) => void;
  userEmail?: string;
}

export default function SettingsTab({
  rateLimit,
  setRateLimit,
  enforceStrictSsl,
  setEnforceStrictSsl,
  sessionTimeout,
  setSessionTimeout,
  showToast,
  userEmail
}: SettingsTabProps) {
  const { config, setGatewayUrl, setAdminKey, setVirtualKey, saveAdminKeyForEmail } = useGateway();

  // Local draft state so edits aren't committed to sessionStorage/context
  // until "Save Connection" is pressed.
  const [draftGatewayUrl, setDraftGatewayUrl] = useState(config.gatewayUrl);
  const [draftAdminKey, setDraftAdminKey] = useState(config.adminKey);
  const [draftVirtualKey, setDraftVirtualKey] = useState(config.virtualKey);

  const [testState, setTestState] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle');
  const [testChecks, setTestChecks] = useState<Record<string, boolean> | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const handleSaveConnection = async () => {
    const trimmedAdminKey = draftAdminKey.trim();
    setGatewayUrl(draftGatewayUrl.trim() || 'http://localhost:8000');
    setAdminKey(trimmedAdminKey);
    setVirtualKey(draftVirtualKey.trim());

    // Also remember this key against the signed-in admin's email on the
    // gateway itself (gateway/auth/admin_account_store.py), so it doesn't
    // need to be re-entered on the next browser session.
    if (trimmedAdminKey && userEmail) {
      const saved = await saveAdminKeyForEmail(userEmail, trimmedAdminKey);
      showToast(
        saved
          ? `Gateway connection saved -- remembered for ${userEmail}`
          : 'Gateway connection saved for this browser session (failed to remember it on the gateway)'
      );
    } else {
      showToast('Gateway connection saved for this browser session');
    }
  };

  const handleTestConnection = async () => {
    // Test against whatever is currently saved in context (so Save first,
    // then Test, reflects what the rest of the app will actually use).
    setTestState('testing');
    setTestChecks(null);
    setTestError(null);
    try {
      const res = await fetch('/api/health/ready', {
        headers: { 'x-monoai-gateway-url': draftGatewayUrl.trim() || config.gatewayUrl },
      });
      const data = await res.json();
      if (res.ok && data.status === 'ok') {
        setTestState('ok');
        setTestChecks(data.checks || {});
      } else {
        setTestState('fail');
        setTestChecks(data.checks || null);
        setTestError(data.status === 'not_ready' ? 'Gateway reports not_ready' : (data.error || `HTTP ${res.status}`));
      }
    } catch (err: any) {
      setTestState('fail');
      setTestError(err.message || 'Failed to reach the gateway');
    }
  };

  return (
    <div className="space-y-6">

      {/* GATEWAY CONNECTION -- the real, backend-backed panel */}
      <div className="bg-[#070c14] border border-white/[0.06] p-5 rounded-[2px] space-y-4">
        <div className="flex items-center space-x-2">
          <Plug size={16} className="text-rose-400" />
          <span className="text-xs font-mono font-bold uppercase text-white/90">Gateway Connection</span>
        </div>
        <p className="text-[11px] text-white/40 leading-relaxed max-w-2xl">
          Paste your MonoAI gateway's admin key here to authenticate this console. It is sent only to this
          app's own server (never to your browser's network tab in plaintext beyond this origin). This browser
          tab keeps it in <strong className="text-white/60">sessionStorage</strong> (cleared on tab close), and
          saving it also remembers it on the gateway itself against{' '}
          <strong className="text-white/60">{userEmail || 'your admin email'}</strong>, so you won't have to
          paste it again on your next sign-in from any browser. Anyone who can reach this gateway and knows that
          email can recall the key the same way — treat it like a shared local/dev secret, not a production one.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">

          <div className="space-y-1 md:col-span-2">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Gateway Base URL</label>
            <input
              type="text"
              value={draftGatewayUrl}
              onChange={(e) => setDraftGatewayUrl(e.target.value)}
              placeholder="http://localhost:8000"
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none transition-colors"
            />
          </div>

          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Admin API Key</label>
            <input
              type="password"
              value={draftAdminKey}
              onChange={(e) => setDraftAdminKey(e.target.value)}
              placeholder="Paste MONOAI_ADMIN_KEY value"
              autoComplete="off"
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none transition-colors"
            />
          </div>

          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Chat Virtual Key (optional)</label>
            <input
              type="password"
              value={draftVirtualKey}
              onChange={(e) => setDraftVirtualKey(e.target.value)}
              placeholder="vk_... (used by the Chat workspace)"
              autoComplete="off"
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none transition-colors"
            />
          </div>

        </div>

        <div className="border-t border-white/5 pt-4 flex flex-wrap items-center justify-between gap-3">
          <button
            onClick={handleTestConnection}
            disabled={testState === 'testing'}
            className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 rounded-[1px] font-mono text-xs hover:bg-indigo-500/15 transition-colors cursor-pointer disabled:opacity-50"
          >
            {testState === 'testing' ? <Loader2 size={13} className="animate-spin" /> : <Plug size={13} />}
            <span>TEST CONNECTION</span>
          </button>

          <button
            onClick={handleSaveConnection}
            className="flex items-center space-x-1.5 px-4 py-2 bg-rose-500/10 border border-rose-500/30 text-rose-300 rounded-[1px] font-mono text-xs hover:bg-rose-500/15 transition-colors cursor-pointer"
          >
            <Save size={13} />
            <span>SAVE CONNECTION</span>
          </button>
        </div>

        {testState !== 'idle' && testState !== 'testing' && (
          <div className={`p-3 rounded-[1px] border text-xs font-mono space-y-2 ${
            testState === 'ok' ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-rose-500/5 border-rose-500/20'
          }`}>
            <div className="flex items-center space-x-2">
              {testState === 'ok' ? (
                <CheckCircle2 size={14} className="text-emerald-400" />
              ) : (
                <XCircle size={14} className="text-rose-400" />
              )}
              <span className={testState === 'ok' ? 'text-emerald-300' : 'text-rose-300'}>
                {testState === 'ok' ? 'Gateway is ready' : `Gateway not ready${testError ? `: ${testError}` : ''}`}
              </span>
            </div>
            {testChecks && (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1">
                {Object.entries(testChecks).map(([check, ok]) => (
                  <div key={check} className="flex items-center justify-between px-2 py-1 bg-black/20 border border-white/5 rounded-[1px]">
                    <span className="text-white/50">{check}</span>
                    <span className={ok ? 'text-emerald-400' : 'text-rose-400'}>{ok ? 'OK' : 'DOWN'}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* COSMETIC LOCAL PREFERENCES -- not backed by any gateway endpoint */}
      <div className="bg-[#070c14] border border-white/[0.06] p-5 rounded-[2px] space-y-4">
        <div className="flex items-center space-x-2">
          <SettingsIcon size={16} className="text-white/40" />
          <span className="text-xs font-mono font-bold uppercase text-white/70">Console Preferences (local only)</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">

          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Global Rate Limit Threshold (RPM per operator)</label>
            <input
              type="number"
              value={rateLimit}
              onChange={(e) => setRateLimit(e.target.value)}
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none transition-colors"
            />
          </div>

          <div className="flex items-center justify-between border border-white/5 bg-white/[0.01] p-3 rounded-[1px]">
            <div className="space-y-0.5">
              <span className="text-xs text-white/90 block">Strict TLS Certificate Validation</span>
              <span className="text-[10px] font-mono text-white/30 block">Rejects unsigned or custom-signed cert pools</span>
            </div>
            <button
              onClick={() => setEnforceStrictSsl(!enforceStrictSsl)}
              className={`w-8 h-4 rounded-full transition-colors relative cursor-pointer ${enforceStrictSsl ? 'bg-indigo-500' : 'bg-white/10'}`}
            >
              <span className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${enforceStrictSsl ? 'left-4.5' : 'left-0.5'}`} />
            </button>
          </div>

          <div className="space-y-1">
            <label className="text-[10px] font-mono text-white/45 uppercase block">Admin Token Idle Expiration (Minutes)</label>
            <select
              value={sessionTimeout}
              onChange={(e) => setSessionTimeout(e.target.value)}
              className="w-full bg-[#030509] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/90 focus:outline-none transition-colors cursor-pointer"
            >
              <option value="5">5 Minutes</option>
              <option value="15">15 Minutes (Standard)</option>
              <option value="60">60 Minutes</option>
              <option value="360">24 Hours</option>
            </select>
          </div>

        </div>

        <div className="border-t border-white/5 pt-4 flex justify-end">
          <button
            onClick={() => showToast('Local console preferences updated (not sent to any backend)')}
            className="flex items-center space-x-1.5 px-4 py-2 bg-white/5 border border-white/10 text-white/60 rounded-[1px] font-mono text-xs hover:bg-white/10 transition-colors cursor-pointer"
          >
            <Save size={13} />
            <span>SAVE PREFERENCES</span>
          </button>
        </div>

      </div>

      {/* INTEGRATION SIEM SPECIFICATION -- mock, no backend source (non-goal) */}
      <div className="bg-[#070b11] border border-white/[0.08] p-5 rounded-[2px] space-y-3">
        <div className="flex items-center space-x-2">
          <Database size={15} className="text-indigo-400" />
          <span className="text-xs font-mono font-bold uppercase text-white/80">Active SIEM & Webhook Forwarders</span>
        </div>
        <p className="text-xs text-white/45">
          Secure tunnels configured to feed raw transaction trace logs directly to audit clusters (Splunk, Datadog).
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
          <div className="border border-white/5 p-3 rounded-[1px] bg-[#05080c] flex items-center justify-between">
            <div className="font-mono text-xs">
              <div className="text-white/80">Splunk Cloud Pipeline</div>
              <div className="text-white/30 text-[10px]">Endpoint: https://hec.splunk.monoai:8088</div>
            </div>
            <span className="text-[9px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1 py-0.2 rounded-[1px]">OPERATIONAL</span>
          </div>
          <div className="border border-white/5 p-3 rounded-[1px] bg-[#05080c] flex items-center justify-between">
            <div className="font-mono text-xs">
              <div className="text-white/80">Datadog Core Log Stream</div>
              <div className="text-white/30 text-[10px]">Endpoint: https://http-intake.logs.datadoghq.com</div>
            </div>
            <span className="text-[9px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1 py-0.2 rounded-[1px]">OPERATIONAL</span>
          </div>
        </div>
      </div>

    </div>
  );
}
