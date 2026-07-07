import React, { useState } from 'react';
import {
  Coins,
  Download,
  AlertTriangle,
  Search,
  UserCheck,
  ChevronUp,
  ChevronDown,
  Check
} from 'lucide-react';
import { UserRecord } from '../../types';

interface OverviewTabProps {
  stats: {
    requestsToday: number;
    blockedCount: number;
    redactedCount: number;
    activeRoles: number;
    activePolicies: number;
  };
  users: UserRecord[];
  alertThresholdPct: number;
  setAlertThresholdPct: (val: number) => void;
  dismissedAlertIds: string[];
  thresholdAlerts: Array<{
    userId: string;
    user: UserRecord;
    percentage: number;
    isBreach: boolean;
  }>;
  activeAlertsCount: number;
  resetAlerts: () => void;
  simulateTrafficForUser: (userId: string) => void;
  dismissAlert: (userId: string) => void;
  resetUserCost: (userId: string) => void;
  handleExportCSV: () => void;
  updateUserCostLimit: (userId: string, limit: number) => void;
  showToast: (msg: string) => void;
}

export default function OverviewTab({
  stats,
  users,
  alertThresholdPct,
  setAlertThresholdPct,
  dismissedAlertIds,
  thresholdAlerts,
  activeAlertsCount,
  resetAlerts,
  simulateTrafficForUser,
  dismissAlert,
  resetUserCost,
  handleExportCSV,
  updateUserCostLimit,
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
                    .filter(alert => !dismissedAlertIds.includes(alert.userId))
                    .map(({ userId, user: u, percentage, isBreach }) => (
                      <div
                        key={userId}
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
                              <span className="text-xs font-semibold text-white/90">{u.name}</span>
                              <span className="text-[9px] font-mono text-white/40">({u.email})</span>
                              <span className={`text-[8px] font-mono font-bold px-1.5 py-0.2 border rounded-[1px] uppercase ${
                                isBreach
                                  ? 'text-rose-400 border-rose-500/25 bg-rose-500/5'
                                  : 'text-amber-300 border-amber-500/20 bg-amber-500/5'
                              }`}>
                                {isBreach ? 'CRITICAL BREACH' : `${alertThresholdPct}% CEILING EXCEEDED`}
                              </span>
                            </div>
                            <div className="text-[10px] font-mono text-white/40 mt-0.5">
                              Quota Consumption: <strong className={isBreach ? 'text-rose-400' : 'text-amber-400'}>${(u.totalCost || 0).toFixed(2)}</strong> of ${u.costLimit.toFixed(2)} limit ({percentage.toFixed(1)}%)
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center space-x-2 self-end sm:self-auto shrink-0">
                          <button
                            onClick={() => simulateTrafficForUser(userId)}
                            className="px-2 py-1 bg-white/5 hover:bg-white/10 border border-white/10 text-white/70 hover:text-white rounded-[1px] text-[10px] font-mono transition-all flex items-center space-x-1 cursor-pointer"
                            title="Inject a spike of random user API queries"
                          >
                            <span>⚡ INJECT_SPEND</span>
                          </button>
                          <button
                            onClick={() => dismissAlert(userId)}
                            className="px-2 py-1 bg-white/5 hover:bg-[#121620] border border-white/10 text-white/40 hover:text-white/80 rounded-[1px] text-[10px] font-mono transition-all cursor-pointer"
                          >
                            MUTE
                          </button>
                          <button
                            onClick={() => {
                              if (window.confirm(`Are you sure you want to reset all token spend counters for ${u.name}?`)) {
                                resetUserCost(userId);
                              }
                            }}
                            className="px-2 py-1 border border-rose-500/10 hover:border-rose-500/20 bg-rose-500/5 text-rose-400 hover:text-rose-300 rounded-[1px] text-[10px] font-mono transition-all cursor-pointer"
                          >
                            RESET
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
              {users
                .filter(u => u.name.toLowerCase().includes(userSearchText.toLowerCase()) || u.email.toLowerCase().includes(userSearchText.toLowerCase()))
                .map(u => {
                  const limitPct = (u.costLimit || 0) > 0 ? ((u.totalCost || 0) / (u.costLimit || 0)) * 100 : 0;
                  return (
                    <div key={u.id} className="p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-white/[0.01] transition-colors">
                      
                      {/* Left: User metadata */}
                      <div className="flex items-center space-x-3 min-w-0">
                        <div className="p-1.5 bg-white/5 rounded-[1px]">
                          <UserCheck size={14} className={u.status === 'active' ? 'text-indigo-400' : 'text-white/20'} />
                        </div>
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="text-xs font-semibold text-white/90">{u.name}</span>
                            <span className="text-[8px] font-mono px-1 py-0.2 bg-white/5 border border-white/10 text-white/40 rounded-[1px] uppercase">
                              {u.role}
                            </span>
                          </div>
                          <span className="text-[10px] font-mono text-white/40 block truncate">{u.email}</span>
                        </div>
                      </div>

                      {/* Center Left: Token usage details */}
                      <div className="grid grid-cols-2 gap-4 shrink-0 font-mono text-right">
                        <div>
                          <div className="text-[10px] text-white/30 uppercase">Tokens Consumed</div>
                          <div className="text-xs font-semibold text-indigo-300">
                            {((u.inputTokens || 0) + (u.outputTokens || 0)).toLocaleString()}
                          </div>
                          <div className="text-[8px] text-white/20">
                            {u.inputTokens?.toLocaleString()} in / {u.outputTokens?.toLocaleString()} out
                          </div>
                        </div>

                        <div>
                          <div className="text-[10px] text-white/30 uppercase">Cost Spent</div>
                          <div className={`text-xs font-bold ${limitPct >= 100 ? 'text-rose-400' : limitPct >= 85 ? 'text-amber-400' : 'text-emerald-400'}`}>
                            ${(u.totalCost || 0).toFixed(2)}
                          </div>
                          <div className="text-[8px] text-white/20">
                            of ${(u.costLimit || 0).toFixed(2)} Limit
                          </div>
                        </div>
                      </div>

                      {/* Center Right: ProgressBar & interactive limit slider */}
                      <div className="w-full md:w-48 space-y-1">
                        <div className="flex items-center justify-between text-[9px] font-mono text-white/40">
                          <span>Budget Usage</span>
                          <span className={limitPct >= 100 ? 'text-rose-400 font-bold' : 'text-white/60'}>
                            {limitPct.toFixed(0)}%
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

                      {/* Right: Inline Limit Editor & spent cost reset */}
                      <div className="flex items-center space-x-3 shrink-0 self-end md:self-auto">
                        <div className="flex items-center space-x-1.5 bg-black/30 border border-white/5 rounded-[1px] p-1">
                          <span className="text-[10px] font-mono text-white/30">$</span>
                          <input
                            type="number"
                            min="0"
                            step="5"
                            value={u.costLimit || 0}
                            onChange={(e) => updateUserCostLimit(u.id, parseFloat(e.target.value) || 0)}
                            className="w-11 bg-transparent text-[11px] font-mono text-white text-center focus:outline-none"
                            title="Tweak limits inline"
                          />
                          <div className="flex flex-col space-y-0.5">
                            <button 
                              onClick={() => updateUserCostLimit(u.id, (u.costLimit || 0) + 5)}
                              className="p-0.5 hover:bg-white/10 rounded-[1px] text-white/50 hover:text-white"
                            >
                              <ChevronUp size={8} />
                            </button>
                            <button 
                              onClick={() => updateUserCostLimit(u.id, Math.max(0, (u.costLimit || 0) - 5))}
                              className="p-0.5 hover:bg-white/10 rounded-[1px] text-white/50 hover:text-white"
                            >
                              <ChevronDown size={8} />
                            </button>
                          </div>
                        </div>

                        <div className="flex items-center space-x-1">
                          {/* Preset Buttons */}
                          {[25, 50, 100].map(pVal => (
                            <button
                              key={pVal}
                              onClick={() => updateUserCostLimit(u.id, pVal)}
                              className={`px-1.5 py-0.5 rounded-[1px] border text-[9px] font-mono transition-all ${
                                u.costLimit === pVal 
                                  ? 'border-indigo-500/40 bg-indigo-500/10 text-indigo-300' 
                                  : 'border-white/5 bg-white/5 text-white/50 hover:text-white hover:bg-white/10'
                              }`}
                            >
                              ${pVal}
                            </button>
                          ))}
                        </div>

                        {/* Simulate Traffic Button */}
                        <button
                          onClick={() => simulateTrafficForUser(u.id)}
                          className="p-1.5 border border-amber-500/15 hover:border-amber-500/35 hover:bg-amber-500/5 text-amber-400 hover:text-amber-300 rounded-[1px] text-[9px] font-mono transition-all cursor-pointer"
                          title="Simulate LLM request consumption to trigger threshold alarm"
                        >
                          SIMULATE
                        </button>

                        {/* Reset Spent Button */}
                        <button
                          onClick={() => {
                            if (window.confirm(`Are you sure you want to reset accumulated spend and tokens back to 0 for ${u.name}?`)) {
                              resetUserCost(u.id);
                            }
                          }}
                          className="p-1.5 border border-rose-500/10 hover:border-rose-500/30 hover:bg-rose-500/5 text-rose-400 hover:text-rose-300 rounded-[1px] text-[9px] font-mono transition-all"
                          title="Reset Spent Accumulator"
                        >
                          RESET
                        </button>
                      </div>

                    </div>
                  );
                })}
              {users.filter(u => u.name.toLowerCase().includes(userSearchText.toLowerCase()) || u.email.toLowerCase().includes(userSearchText.toLowerCase())).length === 0 && (
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
