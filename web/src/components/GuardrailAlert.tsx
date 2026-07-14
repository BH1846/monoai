import React, { useState } from 'react';
import { 
  ShieldAlert, 
  Lock, 
  Key, 
  Shield, 
  Check, 
  ChevronDown, 
  ChevronUp, 
  Terminal,
  Activity
} from 'lucide-react';
import { GuardrailDecision } from '../types';

interface GuardrailAlertProps {
  decision: GuardrailDecision;
}

export default function GuardrailAlert({ decision }: GuardrailAlertProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { type, status, title, message, details } = decision;

  // Determine styling based on type and status
  let theme = {
    bg: 'bg-rose-950/15 border-rose-500/25 text-rose-200',
    badge: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
    accentColor: 'text-rose-400',
    statusText: 'BLOCKED AT PROXY GATEWAY',
    Icon: Lock,
    accentBorder: 'border-l-2 border-l-rose-500'
  };

  if (status === 'redacted') {
    theme = {
      bg: 'bg-amber-950/10 border-amber-500/25 text-amber-200',
      badge: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
      accentColor: 'text-amber-400',
      statusText: 'PII MASKING ACTIVE',
      Icon: ShieldAlert,
      accentBorder: 'border-l-2 border-l-amber-500'
    };
  } else if (status === 'neutralized') {
    theme = {
      bg: 'bg-violet-950/10 border-violet-500/25 text-violet-200',
      badge: 'bg-violet-500/10 border-violet-500/30 text-violet-400',
      accentColor: 'text-violet-400',
      statusText: 'VULNERABILITY NEUTRALIZED',
      Icon: Shield,
      accentBorder: 'border-l-2 border-l-violet-500'
    };
  } else if (status === 'allowed') {
    theme = {
      bg: 'bg-emerald-950/10 border-emerald-500/20 text-emerald-200',
      badge: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
      accentColor: 'text-emerald-400',
      statusText: 'SCAN PASSED (SECURE)',
      Icon: Shield,
      accentBorder: 'border-l-2 border-l-emerald-500/60'
    };
  }

  if (type === 'info') {
    theme = {
      bg: 'bg-indigo-950/10 border-indigo-500/20 text-indigo-200',
      badge: 'bg-indigo-500/10 border-indigo-500/20 text-indigo-400',
      accentColor: 'text-indigo-400',
      statusText: 'GATEWAY INTELLIGENT AUTO-ROUTE',
      Icon: Activity,
      accentBorder: 'border-l-2 border-l-indigo-500/60'
    };
  }

  const IconComponent = theme.Icon;

  return (
    <div className={`w-full ${theme.bg} border ${theme.accentBorder} rounded-[2px] p-4 mb-4 flex flex-col font-mono transition-all duration-250`}>
      {/* Header Info */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center space-x-2">
          <IconComponent size={14} className={`${theme.accentColor} shrink-0`} />
          <span className={`text-[9px] font-mono font-bold tracking-widest uppercase ${theme.accentColor}`}>
            {theme.statusText}
          </span>
        </div>
        <span className="text-[8px] font-mono uppercase bg-white/5 border border-white/10 px-1.5 py-0.5 rounded-[1px] text-white/50 tracking-wider">
          Torkq Engine v1.4
        </span>
      </div>

      {/* Main Content */}
      <div className="flex flex-col space-y-1 font-sans">
        <h4 className="text-[13px] font-bold text-white/95 leading-snug tracking-tight font-mono">
          {title}
        </h4>
        <p className="text-[12px] text-white/70 leading-relaxed font-light">
          {message}
        </p>
      </div>

      {/* Diagnostic Toggler */}
      {details && details.length > 0 && (
        <div className="mt-3 pt-2.5 border-t border-white/[0.06]">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center space-x-1.5 text-[10px] font-mono text-white/45 hover:text-white/80 transition-colors focus:outline-none cursor-pointer"
          >
            <Activity size={11} className="opacity-70" />
            <span>{isExpanded ? 'Hide Diagnostic Logs' : 'Show Diagnostic Logs'}</span>
            {isExpanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>

          {isExpanded && (
            <div className="mt-2 p-2.5 bg-black/40 border border-white/[0.05] rounded-[1px] font-mono text-[10px] text-white/60 space-y-1 leading-normal select-text">
              {details.map((detail, index) => (
                <div key={index} className="flex items-start space-x-1.5">
                  <span className={`${theme.accentColor} font-bold select-none`}>&gt;</span>
                  <span>{detail}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
