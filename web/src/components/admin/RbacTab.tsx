import React from 'react';
import { ShieldCheck, RefreshCw, Check, X } from 'lucide-react';
import { RbacMatrix } from '../../types';

interface RbacTabProps {
  rbacMatrix: RbacMatrix;
  toggleRbacPermission: (role: string, capability: string) => void;
  modelsAndCapabilities: Array<{ key: string; label: string; type: string }>;
  showToast: (msg: string) => void;
}

export default function RbacTab({
  rbacMatrix,
  toggleRbacPermission,
  modelsAndCapabilities,
  showToast
}: RbacTabProps) {
  return (
    <div className="space-y-6">
      
      <div className="bg-[#070c14] border border-white/[0.06] p-4 rounded-[2px] flex flex-col md:flex-row md:items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <ShieldCheck size={16} className="text-rose-400" />
            <span className="text-xs font-mono font-bold uppercase text-white/90">Gateway Permissions Policy Matrix</span>
          </div>
          <p className="text-xs text-white/45 leading-relaxed">
            This matrix defines real-time API capabilities and backend LLM routing scopes for each identity group.
            Checking/unchecking cells commits policy adjustments immediately to the active gateway clusters.
          </p>
        </div>
        <button
          onClick={() => showToast('RBAC permissions matrix fully synchronized to all multi-region clusters')}
          className="mt-3 md:mt-0 flex items-center space-x-1 px-3 py-1.5 bg-[#0b121c] border border-white/[0.1] hover:bg-white/5 transition-colors rounded-[1px] font-mono text-[10px] text-white/80 shrink-0 self-start md:self-auto cursor-pointer"
        >
          <RefreshCw size={11} className="animate-spin-slow" />
          <span>SYNC GATEWAY CLUSTER</span>
        </button>
      </div>

      {/* GRID permissions matrix */}
      <div className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[700px]">
          <thead>
            <tr className="border-b border-white/[0.08] bg-white/[0.02]">
              <th className="py-3 px-4 font-mono text-[10px] text-white/40 uppercase tracking-wider min-w-[150px]">
                ROLE CLASS ID
              </th>
              {modelsAndCapabilities.map((mc) => (
                <th
                  key={mc.key}
                  className="py-3 px-3 font-mono text-[9px] text-white/50 text-center uppercase tracking-wider"
                >
                  <span className={`block font-bold truncate max-w-[100px] mx-auto text-white/80 ${
                    mc.type === 'model' ? 'text-indigo-300' : 'text-amber-400'
                  }`}>
                    {mc.label}
                  </span>
                  <span className="text-[8px] text-white/30 block mt-0.5">
                    {mc.type.toUpperCase()}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {Object.keys(rbacMatrix).map((role) => (
              <tr key={role} className="hover:bg-white/[0.01]">
                <td className="py-3 px-4 font-mono text-[11px] font-bold text-white/90">
                  <div>{role}</div>
                </td>
                {modelsAndCapabilities.map((mc) => {
                  const isPermitted = rbacMatrix[role]?.[mc.key] ?? false;
                  return (
                    <td key={mc.key} className="py-3 px-3 text-center">
                      <button
                        onClick={() => toggleRbacPermission(role, mc.key)}
                        className={`inline-flex items-center justify-center w-6 h-6 rounded-[2px] transition-colors border cursor-pointer ${
                          isPermitted
                            ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-400 hover:bg-indigo-500/20'
                            : 'bg-white/[0.02] border-white/[0.08] text-white/10 hover:border-white/20'
                        }`}
                        title={`Toggle permission for ${role} on ${mc.label}`}
                      >
                        {isPermitted ? <Check size={12} strokeWidth={3} /> : <X size={10} />}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

    </div>
  );
}
