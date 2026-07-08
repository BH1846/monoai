import React, { useState } from 'react';
import {
  Coins,
  Download,
  AlertTriangle,
  Search,
  UserCheck,
  Check
} from 'lucide-react';
import { VirtualKeyRecord } from '../../types';

interface OverviewTabProps {
  stats: {
    requestsToday: number;
    blockedCount: number;
    redactedCount: number;
    activeRoles: number;
    activePolicies: number;
  };
  keys: VirtualKeyRecord[];
  keysLoading: boolean;
  alertThresholdPct: number;
  setAlertThresholdPct: (val: number) => void;
  dismissedAlertIds: string[];
  thresholdAlerts: Array<{
    keyId: string;
    key: VirtualKeyRecord;
    percentage: number;
    isBreach: boolean;
  }>;
  activeAlertsCount: number;
  resetAlerts: () => void;
  dismissAlert: (keyId: string) => void;
  handleExportCSV: () => void;
  showToast: (msg: string) => void;
}

export default function OverviewTab({
  stats,
  keys,
  keysLoading,
  alertThresholdPct,
  setAlertThresholdPct,
  dismissedAlertIds,
  thresholdAlerts,
  activeAlertsCount,
  resetAlerts,
  dismissAlert,
  handleExportCSV,
  showToast
}: OverviewTabProps) {
  const [userSearchText, setUserSearchText] = useState('');

  return (
    <div className="space-y-6">
      
      {/* COMPACT STAT ROW (MONOSPACE, ACCENTED CODES) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        
        <div className="bg-[#070c14] border border-white/[0.06] p-4 rounded-[2px]">
          <div className="text-[10px] font-mono tracking-wider text-white/40 uppercase">GATEWAY REQUESTS TODAY</div>
          <div className="text-xl font-bold font-mono text-white/90 mt-1">
            {stats.requestsToday.toLocaleString()}
          </div>
          <div className="text-[9px] font-mono text-emerald-400 mt-1 flex items-center space-x-1">
            <span>● OK_PROXY_FLOW</span>
            <span className="text-white/20">|</span>
            <span>100% SLA uptime</span>
          </div>
        </div>

        <div className="bg-[#070c14] border border-white/[0.06] p-4 rounded-[2px]">
          <div className="text-[10px] font-mono tracking-wider text-white/40 uppercase">THREATS INTERCEPTED (BLOCKED)</div>
          <div className="text-xl font-bold font-mono text-rose-400 mt-1 flex items-baseline space-x-2">
            <span>{stats.blockedCount}</span>
            <span className="text-[10px] font-normal text-rose-500/80 bg-rose-500/10 px-1 py-0.2 rounded-[1px]">SHIELD HIGH</span>
          </div>
          <div className="text-[9px] font-mono text-white/30 mt-1">
            Rule matches: DLP, Token injection, CVEs
          </div>
        </div>

        <div className="bg-[#070c14] border border-white/[0.06] p-4 rounded-[2px]">
          <div className="text-[10px] font-mono tracking-wider text-white/40 uppercase">DATA REDACTIONS (PII MASK)</div>
          <div className="text-xl font-bold font-mono text-amber-400 mt-1 flex items-baseline space-x-2">
            <span>{stats.redactedCount}</span>
            <span className="text-[10px] font-normal text-amber-500/80 bg-amber-500/10 px-1 py-0.2 rounded-[1px]">ACTIVE</span>
          </div>
          <div className="text-[9px] font-mono text-white/30 mt-1">
            Pattern matches: SSN, API Keys, Emails
          </div>
        </div>

        <div className="bg-[#070c14] border border-white/[0.06] p-4 rounded-[2px]">
          <div className="text-[10px] font-mono tracking-wider text-white/40 uppercase">GATEWAY CLUSTER CLASSIFICATION</div>
          <div className="text-xl font-bold font-mono text-indigo-400 mt-1">
            {stats.activeRoles} Active Roles
          </div>
          <div className="text-[9px] font-mono text-indigo-400/80 mt-1">
            Dynamic orchestration active (Auto-Route)
          </div>
        </div>

      </div>

      {/* GLOBAL COST & TOKEN BUDGET CONTROL CENTER */}
      <div className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-hidden">
        
        {/* Header */}
        <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between bg-white/[0.01]">
          <div className="flex items-center space-x-2">
            <Coins size={14} className="text-amber-400" />
            <span className="text-[11px] font-mono uppercase tracking-widest font-bold text-white/80">Global Token & Cost Telemetry Control</span>
          </div>
          <div className="flex items-center space-x-4">
            <button
              onClick={handleExportCSV}
              className="flex items-center space-x-1.5 px-2.5 py-1 border border-amber-500/30 bg-amber-500/5 hover:bg-amber-500/10 hover:border-amber-500/50 text-amber-300 rounded-[1px] text-[10px] font-mono transition-all cursor-pointer"
              title="Download comprehensive user spent cost & token report as CSV"
            >
              <Download size={11} />
              <span>EXPORT_USAGE_CSV</span>
            </button>
            <div className="text-[10px] font-mono text-white/40">
              SLA Cost Sync: <strong className="text-emerald-400">ONLINE</strong>
            </div>
          </div>
        </div>

        {/* Inner layout */}
        <div className="p-5 space-y-6">

          {/* THRESHOLD ALERT SYSTEM CONFIG & LIVE ALERT STREAM */}
          <div className="bg-[#05080e] border border-white/[0.05] p-5 rounded-[2px] space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-white/[0.04] pb-3 gap-3">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
                  <span className="text-xs font-mono font-bold uppercase tracking-wider text-white">Realtime Threshold Alerts System</span>
                </div>
                <p className="text-[10px] text-white/40 font-mono mt-0.5">
                  Configure cluster-wide budget guardrails and receive instant toast warnings when operators breach defined ceilings.
                </p>
              </div>
              
              {/* Interactive Threshold Tuner */}
              <div className="flex items-center space-x-1.5 bg-black/40 border border-white/10 rounded-[1px] p-1 self-start sm:self-auto">
                <span className="text-[9px] font-mono text-white/30 px-1 uppercase">Alert Threshold:</span>
                {[75, 80, 85, 90, 95].map((val) => (
                  <button
                    key={val}
                    onClick={() => {
                      setAlertThresholdPct(val);
                      showToast(`Budget alert threshold level calibrated to ${val}%`);
                    }}
                    className={`px-1.5 py-0.5 rounded-[1px] text-[10px] font-mono transition-all cursor-pointer ${
                      alertThresholdPct === val
                        ? 'bg-amber-500/15 border border-amber-500/30 text-amber-300 font-bold'
                        : 'border border-transparent text-white/40 hover:text-white/80'
                    }`}
                  >
                    {val}%
                  </button>
                ))}
              </div>
            </div>

            {/* Active Alerts Streams */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest">Active Budget Exceptions ({activeAlertsCount})</span>
                {dismissedAlertIds.length > 0 && (
                  <button
                    onClick={resetAlerts}
                    className="text-[9px] font-mono text-indigo-400 hover:text-indigo-300 underline cursor-pointer"
                  >
                    Reset dismissed alerts ({dismissedAlertIds.length})
                  </button>
                )}
              </div>

              {activeAlertsCount > 0 ? (
                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {thresholdAlerts
                    .filter(alert => !dismissedAlertIds.includes(alert.keyId))
                    .map(({ keyId, key: k, percentage, isBreach }) => (
                      <div
                        key={keyId}
                        className={`p-3 rounded-[1px] border flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors ${
                          isBreach
                            ? 'bg-rose-500/[0.03] border-rose-500/20 hover:bg-rose-500/[0.05]'
                            : 'bg-amber-500/[0.02] border-amber-500/15 hover:bg-amber-500/[0.04]'
                        }`}
                      >
                        <div className="flex items-start sm:items-center space-x-3">
                          <div className={`p-1 rounded-[1px] ${isBreach ? 'bg-rose-500/10 text-rose-400' : 'bg-amber-500/10 text-amber-400'}`}>
                            <AlertTriangle size={13} className={isBreach ? 'animate-bounce' : ''} />
                          </div>
                          <div>
                            <div className="flex items-center space-x-2 flex-wrap gap-1">
                              <span className="text-xs font-semibold text-white/90">{k.team_id || k.key_id}</span>
                              <span className="text-[9px] font-mono text-white/40">({k.key_id})</span>
                              <span className={`text-[8px] font-mono font-bold px-1.5 py-0.2 border rounded-[1px] uppercase ${
                                isBreach
                                  ? 'text-rose-400 border-rose-500/25 bg-rose-500/5'
                                  : 'text-amber-300 border-amber-500/20 bg-amber-500/5'
                              }`}>
                                {isBreach ? 'CRITICAL BREACH' : `${alertThresholdPct}% CEILING EXCEEDED`}
                              </span>
                            </div>
                            <div className="text-[10px] font-mono text-white/40 mt-0.5">
                              Quota Consumption: <strong className={isBreach ? 'text-rose-400' : 'text-amber-400'}>${k.budget_usd_spent.toFixed(2)}</strong> of ${(k.budget_usd_monthly || 0).toFixed(2)} limit ({percentage.toFixed(1)}%)
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center space-x-2 self-end sm:self-auto shrink-0">
                          <button
                            onClick={() => dismissAlert(keyId)}
                            className="px-2 py-1 bg-white/5 hover:bg-[#121620] border border-white/10 text-white/40 hover:text-white/80 rounded-[1px] text-[10px] font-mono transition-all cursor-pointer"
                          >
                            MUTE
                          </button>
                        </div>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="border border-emerald-500/10 bg-emerald-500/[0.01] rounded-[1px] p-4 flex items-center space-x-3">
                  <div className="p-1 bg-emerald-500/10 text-emerald-400 rounded-full">
                    <Check size={14} />
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-emerald-400 font-mono">ALL OPERATORS UNDER ALLOCATION CHECKS</span>
                    <p className="text-[10px] text-white/30 font-mono mt-0.5">
                      No operators are currently exceeding the defined budget threshold alert level ({alertThresholdPct}%). All traffic streams normal.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Interactive Operator List with inline budget tuning */}
          <div className="space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center space-x-3">
                <span className="text-[11px] font-mono uppercase tracking-widest font-bold text-white/50">Operator Budget Limits Panel</span>
                <button
                  onClick={handleExportCSV}
                  className="flex items-center space-x-1 px-2 py-0.5 border border-white/10 hover:border-white/20 bg-white/5 hover:bg-white/10 text-white/60 hover:text-white rounded-[1px] text-[9px] font-mono transition-all cursor-pointer"
                  title="Download user spent cost & token report as CSV"
                >
                  <Download size={10} />
                  <span>EXPORT_CSV</span>
                </button>
              </div>
              
              {/* Optional local search/filter */}
              <div className="relative w-48">
                <Search className="absolute left-2 top-2 text-white/30" size={10} />
                <input
                  type="text"
                  placeholder="Filter operator name..."
                  value={userSearchText}
                  onChange={(e) => setUserSearchText(e.target.value)}
                  className="w-full bg-black/40 border border-white/10 hover:border-white/20 focus:border-amber-500/30 rounded-[1px] pl-6 pr-2 py-0.5 text-[10px] font-mono text-white/90 placeholder-white/20 focus:outline-none transition-colors"
                />
              </div>
            </div>

            <div className="border border-white/[0.05] bg-[#04080d] divide-y divide-white/[0.04] rounded-[1px]">
              {keysLoading && keys.length === 0 && (
                <div className="p-8 text-center text-white/30 font-mono text-xs">Loading operators...</div>
              )}
              {!keysLoading && keys.length === 0 && (
                <div className="p-8 text-center text-white/30 font-mono text-xs">
                  No virtual keys registered yet -- create one in the Users tab to see budget telemetry here.
                </div>
              )}
              {keys
                .filter(k => (k.team_id || '').toLowerCase().includes(userSearchText.toLowerCase()) || k.key_id.toLowerCase().includes(userSearchText.toLowerCase()))
                .map(k => {
                  const monthly = k.budget_usd_monthly || 0;
                  const limitPct = monthly > 0 ? (k.budget_usd_spent / monthly) * 100 : 0;
                  return (
                    <div key={k.key_id} className="p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-white/[0.01] transition-colors">

                      {/* Left: Key/operator metadata */}
                      <div className="flex items-center space-x-3 min-w-0">
                        <div className="p-1.5 bg-white/5 rounded-[1px]">
                          <UserCheck size={14} className={k.active ? 'text-indigo-400' : 'text-white/20'} />
                        </div>
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="text-xs font-semibold text-white/90">{k.team_id || k.key_id}</span>
                            <span className="text-[8px] font-mono px-1 py-0.2 bg-white/5 border border-white/10 text-white/40 rounded-[1px] uppercase">
                              {k.policy_id}
                            </span>
                            {!k.active && (
                              <span className="text-[8px] font-mono px-1 py-0.2 bg-white/5 border border-white/10 text-white/35 rounded-[1px] uppercase">
                                REVOKED
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] font-mono text-white/40 block truncate">{k.key_id}</span>
                        </div>
                      </div>

                      {/* Center: Cost telemetry */}
                      <div className="shrink-0 font-mono text-right">
                        <div className="text-[10px] text-white/30 uppercase">Cost Spent</div>
                        <div className={`text-xs font-bold ${limitPct >= 100 ? 'text-rose-400' : limitPct >= 85 ? 'text-amber-400' : 'text-emerald-400'}`}>
                          ${k.budget_usd_spent.toFixed(2)}
                        </div>
                        <div className="text-[8px] text-white/20">
                          {monthly > 0 ? `of $${monthly.toFixed(2)} limit` : 'unlimited'}
                        </div>
                      </div>

                      {/* Right: ProgressBar */}
                      <div className="w-full md:w-48 space-y-1">
                        <div className="flex items-center justify-between text-[9px] font-mono text-white/40">
                          <span>Budget Usage</span>
                          <span className={limitPct >= 100 ? 'text-rose-400 font-bold' : 'text-white/60'}>
                            {monthly > 0 ? `${limitPct.toFixed(0)}%` : '—'}
                          </span>
                        </div>
                        <div className="w-full bg-white/[0.04] h-1.5 rounded-[1px] overflow-hidden relative">
                          <div
                            className={`h-full rounded-[1px] transition-all duration-300 ${
                              limitPct >= 100 ? 'bg-rose-500 animate-pulse' : limitPct >= 85 ? 'bg-amber-400' : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.min(limitPct, 100)}%` }}
                          />
                        </div>
                        {limitPct >= 100 && (
                          <div className="text-[8px] font-mono text-rose-400 tracking-tight animate-pulse leading-none flex items-center space-x-1">
                            <AlertTriangle size={8} />
                            <span>THROTTLE ACTIVE: OVER LIMIT</span>
                          </div>
                        )}
                      </div>

                    </div>
                  );
                })}
              {keys.length > 0 && keys.filter(k => (k.team_id || '').toLowerCase().includes(userSearchText.toLowerCase()) || k.key_id.toLowerCase().includes(userSearchText.toLowerCase())).length === 0 && (
                <div className="p-8 text-center text-white/30 font-mono text-xs">
                  No operators matching "{userSearchText}" found in gateway roster.
                </div>
              )}
            </div>
          </div>

        </div>

      </div>

    </div>
  );
}
