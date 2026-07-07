import React from 'react';
import { SlidersHorizontal, Search, RefreshCw } from 'lucide-react';
import { AuditEvent } from '../../types';

interface AuditLogTabProps {
  auditFilters: {
    decision: string;
    rule: string;
    user: string;
    search: string;
  };
  setAuditFilters: React.Dispatch<React.SetStateAction<{
    decision: string;
    rule: string;
    user: string;
    search: string;
  }>>;
  uniqueUsersInEvents: string[];
  filteredAuditEvents: AuditEvent[];
  expandedEventId: string | null;
  setExpandedEventId: (id: string | null) => void;
  showToast: (msg: string) => void;
}

export default function AuditLogTab({
  auditFilters,
  setAuditFilters,
  uniqueUsersInEvents,
  filteredAuditEvents,
  expandedEventId,
  setExpandedEventId,
  showToast
}: AuditLogTabProps) {
  return (
    <div className="space-y-4">
      
      {/* FILTERS TOOLBAR */}
      <div className="bg-[#070c14] border border-white/[0.08] p-4 rounded-[2px] space-y-3">
        <div className="flex items-center justify-between border-b border-white/5 pb-2">
          <div className="flex items-center space-x-2">
            <SlidersHorizontal size={13} className="text-white/40" />
            <span className="text-[10px] font-mono font-bold tracking-widest text-white/50 uppercase">Filter Audit Stream</span>
          </div>
          <button
            onClick={() => {
              setAuditFilters({ decision: 'ALL', rule: 'ALL', user: 'ALL', search: '' });
              showToast('Audit log filters reset');
            }}
            className="text-[10px] font-mono text-rose-400/80 hover:text-rose-400 transition-colors cursor-pointer"
          >
            Reset Filter Parameters
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          
          {/* Search bar */}
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 text-white/30" size={13} />
            <input
              type="text"
              placeholder="Search ID, payload details..."
              value={auditFilters.search}
              onChange={(e) => setAuditFilters(prev => ({ ...prev, search: e.target.value }))}
              className="w-full bg-white/[0.02] hover:bg-white/[0.04] focus:bg-[#04080c] border border-white/[0.1] focus:border-rose-500/30 rounded-[2px] pl-8 pr-3 py-1.5 text-xs font-mono text-white/90 placeholder-white/20 focus:outline-none transition-colors"
            />
          </div>

          {/* Decision select */}
          <div>
            <select
              value={auditFilters.decision}
              onChange={(e) => setAuditFilters(prev => ({ ...prev, decision: e.target.value }))}
              className="w-full bg-[#070c14] border border-white/[0.1] hover:border-white/20 focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/95 focus:outline-none transition-colors cursor-pointer"
            >
              <option value="ALL">ALL DECISIONS</option>
              <option value="ALLOWED">ALLOWED ONLY</option>
              <option value="BLOCKED">BLOCKED ONLY</option>
              <option value="REDACTED">REDACTED ONLY</option>
            </select>
          </div>

          {/* Rule type select */}
          <div>
            <select
              value={auditFilters.rule}
              onChange={(e) => setAuditFilters(prev => ({ ...prev, rule: e.target.value }))}
              className="w-full bg-[#070c14] border border-white/[0.1] hover:border-white/20 focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/95 focus:outline-none transition-colors cursor-pointer"
            >
              <option value="ALL">ALL RULE TYPES</option>
              <option value="RBAC">RBAC RULE</option>
              <option value="PII_SCAN">PII SCAN</option>
              <option value="SECRET_SCAN">SECRET SCAN</option>
              <option value="CODE_VULN">CODE VULNERABILITY</option>
            </select>
          </div>

          {/* User select */}
          <div>
            <select
              value={auditFilters.user}
              onChange={(e) => setAuditFilters(prev => ({ ...prev, user: e.target.value }))}
              className="w-full bg-[#070c14] border border-white/[0.1] hover:border-white/20 focus:border-rose-500/30 rounded-[2px] px-3 py-1.5 text-xs font-mono text-white/95 focus:outline-none transition-colors cursor-pointer"
            >
              <option value="ALL">ALL USERS / CONSUMERS</option>
              {uniqueUsersInEvents.map(u => (
                <option key={u} value={u}>{u.split('@')[0]} ({u})</option>
              ))}
            </select>
          </div>

        </div>
      </div>

      {/* COMPACT DENSE TABLE */}
      <div className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-white/[0.08] bg-white/[0.02] text-white/40 font-mono text-[9px] uppercase tracking-wider">
              <th className="py-2.5 px-4">Event ID / Time</th>
              <th className="py-2.5 px-4">Gateway Decision</th>
              <th className="py-2.5 px-4">Rule Intercepted</th>
              <th className="py-2.5 px-4">Inbound Operator</th>
              <th className="py-2.5 px-4">Target Model</th>
              <th className="py-2.5 px-4">Scanned Content Payload</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {filteredAuditEvents.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-white/30 font-mono text-xs">
                  No events logged yet matching filter parameters. Activity will appear here once requests start flowing.
                </td>
              </tr>
            ) : (
              filteredAuditEvents.map((evt) => {
                let decisionStyle = 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5';
                if (evt.decision === 'BLOCKED') decisionStyle = 'text-rose-400 border-rose-500/20 bg-rose-500/5';
                if (evt.decision === 'REDACTED') decisionStyle = 'text-amber-400 border-amber-500/20 bg-amber-500/5';

                const isExpanded = expandedEventId === evt.id;

                return (
                  <React.Fragment key={evt.id}>
                    <tr
                      onClick={() => setExpandedEventId(isExpanded ? null : evt.id)}
                      className={`hover:bg-white/[0.02] cursor-pointer transition-colors ${
                        isExpanded ? 'bg-white/[0.01]' : ''
                      }`}
                    >
                      <td className="py-3 px-4 font-mono text-[10px] space-y-0.5 whitespace-nowrap">
                        <div className="text-white/80 font-bold">{evt.id}</div>
                        <div className="text-white/30 text-[9px]">{evt.timestamp.replace('T', ' ').replace('Z', '')}</div>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`text-[10px] font-mono font-bold tracking-wider px-2 py-0.5 border rounded-[1px] ${decisionStyle}`}>
                          {evt.decision}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-[11px] text-indigo-300 font-bold">
                        {evt.rule}
                      </td>
                      <td className="py-3 px-4 font-mono text-[10px] text-white/70">
                        {evt.user}
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-[10px] font-mono px-1.5 py-0.2 bg-white/5 border border-white/10 text-white/50 rounded-[1px]">
                          {evt.model}
                        </span>
                      </td>
                      <td className="py-3 px-4 max-w-sm truncate text-xs text-white/80">
                        <div className="flex items-center justify-between">
                          <span className="truncate">{evt.detail}</span>
                          <span className="text-[9px] text-rose-400 font-mono ml-2 shrink-0">
                            {isExpanded ? '[COL_TRACE]' : '[EXP_TRACE]'}
                          </span>
                        </div>
                      </td>
                    </tr>

                    {/* EXPANDED SYSTEM TRACE DETAIL */}
                    {isExpanded && (
                      <tr>
                        <td colSpan={6} className="bg-[#05080c] px-6 py-4 border-t border-b border-white/[0.05]">
                          <div className="bg-[#030509] border border-white/[0.06] rounded-[2px] p-4 space-y-3 font-mono text-xs">
                            <div className="flex items-center justify-between border-b border-white/5 pb-2 text-[10px] text-white/40">
                              <span>GATEWAY TRANSACTION CONSOLE</span>
                              <span>ID: tx_sha256_{evt.id}</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <div className="space-y-1">
                                <span className="text-[10px] text-white/30 block">SOURCE CONTEXT</span>
                                <div className="bg-white/[0.01] p-2 border border-white/[0.04] rounded-[1px]">
                                  <div className="text-white/90 font-mono text-[11px]">Operator: {evt.user}</div>
                                  <div className="text-white/60 font-mono text-[10px] mt-1">Cluster Role Access: Developer Policy Mode</div>
                                </div>
                              </div>

                              <div className="space-y-1">
                                <span className="text-[10px] text-white/30 block">DESTINATION SCOPE</span>
                                <div className="bg-white/[0.01] p-2 border border-white/[0.04] rounded-[1px]">
                                  <div className="text-white/90 font-mono text-[11px]">Routed Endpoint: {evt.model}</div>
                                  <div className="text-white/60 font-mono text-[10px] mt-1">Inference Gateway Tunnel: Active TLS 1.3</div>
                                </div>
                              </div>
                            </div>

                            <div className="space-y-1">
                              <span className="text-[10px] text-white/30 block">GATEWAY DECISION REASONING TRACE</span>
                              <p className="text-rose-200 text-[11px] leading-relaxed bg-rose-950/10 border border-rose-500/10 p-2.5 rounded-[1px]">
                                {evt.detail}
                              </p>
                            </div>

                            <div className="flex items-center space-x-2 pt-1 text-[10px]">
                              <span className="text-white/30">Action Tag:</span>
                              <span className="text-rose-400 font-bold underline bg-rose-500/5 px-1 rounded-[1px]">LOGGED_TO_SIEM</span>
                              <span className="text-white/20">|</span>
                              <span className="text-indigo-400 font-bold underline bg-indigo-500/5 px-1 rounded-[1px]">POLICY_RULE_ENFORCED</span>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

    </div>
  );
}
