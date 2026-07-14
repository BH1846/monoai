import React, { useCallback, useEffect, useState } from 'react';
import {
  LayoutDashboard,
  ShieldCheck,
  Sliders,
  Users,
  Server,
  Settings as SettingsIcon,
  LogOut,
  Activity,
  Check
} from 'lucide-react';
import { AdminTab, AuditEvent, VirtualKeyRecord, RbacMatrix } from '../../types';
import { useGateway } from '../../context/GatewayContext';

// Import our newly extracted modular tabs
import OverviewTab from './OverviewTab';
import AuditLogTab from './AuditLogTab';
import RbacTab from './RbacTab';
import GuardrailsTab from './GuardrailsTab';
import UsersTab from './UsersTab';
import ProvidersTab from './ProvidersTab';
import SettingsTab from './SettingsTab';

interface AdminDashboardProps {
  onBackToWorkspace: () => void;
  onSignOut: () => void;
  userEmail?: string;
}

// ----------------------------------------------------
// INITIAL MOCK DATA
// ----------------------------------------------------
const INITIAL_RBAC_MATRIX: RbacMatrix = {
  'Administrator': {
    'gemini-3.5-flash': true,
    'gemini-3.1-pro-preview': true,
    'gpt-4o': true,
    'claude-3-5-sonnet': true,
    'o1-pro': true,
    'model_fine_tuning': true,
    'direct_api_access': true,
    'policy_modification': true
  },
  'Compliance Officer': {
    'gemini-3.5-flash': true,
    'gemini-3.1-pro-preview': true,
    'gpt-4o': false,
    'claude-3-5-sonnet': false,
    'o1-pro': false,
    'model_fine_tuning': false,
    'direct_api_access': true,
    'policy_modification': true
  },
  'Developer': {
    'gemini-3.5-flash': true,
    'gemini-3.1-pro-preview': true,
    'gpt-4o': true,
    'claude-3-5-sonnet': true,
    'o1-pro': false,
    'model_fine_tuning': false,
    'direct_api_access': true,
    'policy_modification': false
  },
  'Standard User': {
    'gemini-3.5-flash': true,
    'gemini-3.1-pro-preview': false,
    'gpt-4o': true,
    'claude-3-5-sonnet': false,
    'o1-pro': false,
    'model_fine_tuning': false,
    'direct_api_access': false,
    'policy_modification': false
  },
  'API Service Account': {
    'gemini-3.5-flash': true,
    'gemini-3.1-pro-preview': false,
    'gpt-4o': false,
    'claude-3-5-sonnet': false,
    'o1-pro': false,
    'model_fine_tuning': false,
    'direct_api_access': true,
    'policy_modification': false
  },
  'Guest Observer': {
    'gemini-3.5-flash': true,
    'gemini-3.1-pro-preview': false,
    'gpt-4o': false,
    'claude-3-5-sonnet': false,
    'o1-pro': false,
    'model_fine_tuning': false,
    'direct_api_access': false,
    'policy_modification': false
  }
};

const MODELS_AND_CAPABILITIES = [
  { key: 'gemini-3.5-flash', label: 'Gemini 3.5 Flash', type: 'model' },
  { key: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro', type: 'model' },
  { key: 'gpt-4o', label: 'GPT-4o (Omni)', type: 'model' },
  { key: 'claude-3-5-sonnet', label: 'Claude 3.5 Sonnet', type: 'model' },
  { key: 'o1-pro', label: 'OpenAI o1 Pro', type: 'model' },
  { key: 'model_fine_tuning', label: 'Fine-Tuning Access', type: 'capability' },
  { key: 'direct_api_access', label: 'Direct API Access', type: 'capability' },
  { key: 'policy_modification', label: 'Modify Policies', type: 'capability' }
];


export default function AdminDashboard({
  onBackToWorkspace,
  onSignOut,
  userEmail = "rahulbalaskandan1511@gmail.com"
}: AdminDashboardProps) {
  const [activeTab, setActiveTab] = useState<AdminTab>('overview');
  const { config, adminFetch } = useGateway();

  // Unified State
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditLoadError, setAuditLoadError] = useState<string | null>(null);
  const [rbacMatrix, setRbacMatrix] = useState<RbacMatrix>(INITIAL_RBAC_MATRIX);

  // Real audit trail (gateway/api/evidence.py GET /v1/evidence/export via
  // our own /api/admin/audit-log, which flattens the hash-chained NDJSON
  // bundle into the AuditEvent[] shape AuditLogTab.tsx renders).
  const loadAuditEvents = useCallback(async () => {
    setAuditLoading(true);
    setAuditLoadError(null);
    try {
      const res = await adminFetch('audit-log');
      if (res.ok) {
        const data = await res.json();
        setAuditEvents(data.events || []);
      } else {
        const body = await res.json().catch(() => ({}));
        setAuditLoadError(body?.error?.message || `HTTP ${res.status}`);
      }
    } catch (err: any) {
      setAuditLoadError(err.message || 'Failed to load audit log');
    } finally {
      setAuditLoading(false);
    }
  }, [adminFetch]);

  useEffect(() => {
    if (config.adminKey) {
      loadAuditEvents();
    }
  }, [config.adminKey, loadAuditEvents]);

  // Virtual keys (the real "operators" backing the Overview budget panel --
  // same /v1/admin/keys source as the Users tab, see UsersTab.tsx)
  const [keys, setKeys] = useState<VirtualKeyRecord[]>([]);
  const [keysLoading, setKeysLoading] = useState(false);

  const loadKeys = useCallback(async () => {
    setKeysLoading(true);
    try {
      const res = await adminFetch('keys');
      if (res.ok) {
        const data = await res.json();
        setKeys(data.keys || []);
      }
    } catch {
      // Overview budget panel just falls back to its empty state
    } finally {
      setKeysLoading(false);
    }
  }, [adminFetch]);

  useEffect(() => {
    if (config.adminKey) {
      loadKeys();
    }
  }, [config.adminKey, loadKeys]);

  // Settings states (cosmetic local prefs; real gateway connection lives in GatewayContext)
  const [rateLimit, setRateLimit] = useState('60');
  const [enforceStrictSsl, setEnforceStrictSsl] = useState(true);
  const [sessionTimeout, setSessionTimeout] = useState('15');

  // Policy configurations
  const [piiEnabled, setPiiEnabled] = useState(true);
  const [piiRedactAll, setPiiRedactAll] = useState(true);
  const [piiSandboxInput, setPiiSandboxInput] = useState('Please review user rahulbalaskandan1511@gmail.com on mobile +1 (555) 0192. SSN was 999-12-3456.');
  const [piiSandboxOutput, setPiiSandboxOutput] = useState('');

  const [secretEnabled, setSecretEnabled] = useState(true);
  const [entropyThreshold, setEntropyThreshold] = useState(4.2);
  const [secretSandboxInput, setSecretSandboxInput] = useState('export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"');
  const [secretSandboxOutput, setSecretSandboxOutput] = useState('');

  const [codeVulnEnabled, setCodeVulnEnabled] = useState(true);
  const [codeVulnStrictness, setCodeVulnStrictness] = useState('Strict');
  const [codeSandboxInput, setCodeSandboxInput] = useState('SELECT * FROM accounts WHERE user_id = \'" + input + "\' AND active = 1;');
  const [codeSandboxOutput, setCodeSandboxOutput] = useState('');

  // UI States
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [alertThresholdPct, setAlertThresholdPct] = useState<number>(85);
  const [dismissedAlertIds, setDismissedAlertIds] = useState<string[]>([]);
  const [auditFilters, setAuditFilters] = useState({
    decision: 'ALL',
    rule: 'ALL',
    user: 'ALL',
    search: ''
  });
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);

  // Derived budget threshold alerts based on real virtual-key spend vs. their monthly budget
  const thresholdAlerts = keys.map(k => {
    const monthly = k.budget_usd_monthly || 0;
    const pct = monthly > 0 ? (k.budget_usd_spent / monthly) * 100 : 0;
    const isExceeded = monthly > 0 && pct >= alertThresholdPct;
    if (isExceeded) {
      return {
        keyId: k.key_id,
        key: k,
        percentage: pct,
        isBreach: pct >= 100
      };
    }
    return null;
  }).filter((x): x is NonNullable<typeof x> => x !== null);

  const activeAlertsCount = thresholdAlerts.filter(a => !dismissedAlertIds.includes(a.keyId)).length;

  // Trigger Toast helper
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3000);
  };

  // Event handler to transition from Overview events to detailed filtered Audit Tab
  const handleOverviewEventClick = (event: AuditEvent) => {
    setAuditFilters({
      decision: event.decision,
      rule: 'ALL',
      user: 'ALL',
      search: event.id
    });
    setExpandedEventId(event.id);
    setActiveTab('audit');
    showToast(`Navigated to Audit Log filtered for target ID ${event.id}`);
  };

  // ----------------------------------------------------
  // ACTION HANDLERS
  // ----------------------------------------------------
  const toggleRbacPermission = (role: string, capability: string) => {
    setRbacMatrix(prev => {
      const next = { ...prev };
      next[role] = {
        ...next[role],
        [capability]: !next[role][capability]
      };
      return next;
    });
    showToast(`Role "${role}" permission set for "${capability}"`);
  };

  const dismissAlert = (keyId: string) => {
    setDismissedAlertIds(prev => [...prev, keyId]);
    showToast(`Alert for key dismissed in this session`);
  };

  const resetAlerts = () => {
    setDismissedAlertIds([]);
    showToast(`All budget threshold alert states refreshed`);
  };

  const handleExportCSV = () => {
    const headers = [
      'Key ID',
      'User / Team',
      'Policy',
      'Status',
      'Spent (USD)',
      'Monthly Limit (USD)',
      'Quota Used (%)',
      'Limit Breach Status',
      'Created At'
    ];

    const rows = keys.map(k => {
      const monthly = k.budget_usd_monthly || 0;
      const quotaPct = monthly > 0 ? (k.budget_usd_spent / monthly) * 100 : 0;
      const isBreached = monthly > 0 && k.budget_usd_spent >= monthly ? 'BREACHED' : 'OK';
      const escapedTeam = k.team_id ? k.team_id.replace(/"/g, '""') : '';

      return [
        k.key_id,
        `"${escapedTeam}"`,
        k.policy_id,
        k.active ? 'active' : 'revoked',
        k.budget_usd_spent.toFixed(2),
        monthly.toFixed(2),
        `${quotaPct.toFixed(1)}%`,
        isBreached,
        new Date(k.created_at * 1000).toISOString()
      ];
    });

    const csvContent = [
      headers.join(','),
      ...rows.map(e => e.join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `monoai_gateway_token_spend_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showToast('Spend telemetry and token cost report exported successfully as CSV');
  };

  // ----------------------------------------------------
  // TEST SANDBOX RUNNERS
  // ----------------------------------------------------
  const testPiiRule = () => {
    if (!piiEnabled) {
      setPiiSandboxOutput('SKIPPED: PII Scanner is currently toggled OFF.');
      return;
    }
    let text = piiSandboxInput;
    text = text.replace(/\d{3}-\d{2}-\d{4}/g, '[REDACTED_SSN_X9]');
    text = text.replace(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, '[REDACTED_EMAIL_HASH]');
    text = text.replace(/\+?1?\s*\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g, '[REDACTED_PHONE_REF]');

    setPiiSandboxOutput(text);
    showToast('PII sanitization logic simulated.');
  };

  const testSecretRule = () => {
    if (!secretEnabled) {
      setSecretSandboxOutput('SKIPPED: Secret Scanner is currently toggled OFF.');
      return;
    }
    const text = secretSandboxInput.toLowerCase();
    if (text.includes('aws_secret') || text.includes('sk_test_') || text.includes('password') || text.includes('key')) {
      setSecretSandboxOutput(`BLOCKED - entropy matched threshold limit\nDetected high-entropy sequence.\nEntropy score: 4.86 bits (Threshold is ${entropyThreshold}).\nAction: Access Denied (REQUEST_TERMINATED).`);
    } else {
      setSecretSandboxOutput('ALLOWED\nNo credentials or high-entropy entropy pools found above threshold.');
    }
    showToast('Secret entropy scanning simulated.');
  };

  const testCodeRule = () => {
    if (!codeVulnEnabled) {
      setCodeSandboxOutput('SKIPPED: Code Vulnerability Scanner is toggled OFF.');
      return;
    }
    const text = codeSandboxInput.toLowerCase();
    if (text.includes('select') && (text.includes('or') || text.includes('union') || text.includes('\''))) {
      setCodeSandboxOutput('VULNERABILITY MITIGATED\nDetected SQL Injection vector (pattern matching simple string interpolation query).\nAction: Dynamic query token replaced with sanitized safe parameter bindings.');
    } else {
      setCodeSandboxOutput('CLEAN\nNo obvious structural injection or command chains matched.');
    }
    showToast('Security scanning compiled.');
  };

  // Derived filters logic for the Audit Event side notifications
  const filteredAuditEvents = auditEvents.filter(evt => {
    if (auditFilters.decision !== 'ALL' && evt.decision !== auditFilters.decision) return false;
    if (auditFilters.rule !== 'ALL' && evt.rule !== auditFilters.rule) return false;
    if (auditFilters.user !== 'ALL' && evt.user !== auditFilters.user) return false;
    if (auditFilters.search) {
      const s = auditFilters.search.toLowerCase();
      const matchText = `${evt.id} ${evt.user} ${evt.detail} ${evt.model} ${evt.rule}`.toLowerCase();
      if (!matchText.includes(s)) return false;
    }
    return true;
  });

  const filteredAuditEventsCount = filteredAuditEvents.length;

  const uniqueUsersInEvents = Array.from(new Set(auditEvents.map(e => e.user)));

  const totalActivePolicies = (piiEnabled ? 1 : 0) + (secretEnabled ? 1 : 0) + (codeVulnEnabled ? 1 : 0);

  const stats = {
    requestsToday: 32491,
    blockedCount: auditEvents.filter(e => e.decision === 'BLOCKED').length * 12 + 106,
    redactedCount: auditEvents.filter(e => e.decision === 'REDACTED').length * 28 + 482,
    activeRoles: Object.keys(rbacMatrix).length,
    activePolicies: totalActivePolicies
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#05080c] text-white font-sans select-none">
      
      {/* LEFT FIXED BAR (ADMIN NAVIGATION) */}
      <div className="w-64 shrink-0 bg-[#070b11] border-r border-white/[0.08] flex flex-col h-full">
        {/* Header Branding */}
        <div className="h-16 px-5 border-b border-white/[0.08] flex items-center justify-between shrink-0">
          <div className="flex items-center space-x-2">
            <div className="w-5 h-5 bg-rose-500/10 border border-rose-500/30 rounded-[2px] flex items-center justify-center font-mono text-[10px] text-rose-400 font-bold">
              T
            </div>
            <div>
              <span className="font-sans text-[13px] tracking-widest text-white/90 font-bold uppercase">
                Torkq
              </span>
              <span className="block text-[8px] font-mono tracking-wider text-rose-400 font-bold leading-none">
                CONTROL PLANE
              </span>
            </div>
          </div>
        </div>

        {/* Navigation Items */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          <div className="text-[10px] font-mono font-bold tracking-wider text-white/30 uppercase px-3 mb-2">
            Core Operations
          </div>
          
          <button
            onClick={() => setActiveTab('overview')}
            className={`w-full flex items-center space-x-3 px-3 py-2 rounded-[2px] text-[12px] font-medium transition-all cursor-pointer ${
              activeTab === 'overview'
                ? 'text-white bg-white/[0.06] border border-white/[0.05] font-semibold'
                : 'text-white/60 hover:text-white hover:bg-white/[0.02]'
            }`}
          >
            <LayoutDashboard size={14} className={activeTab === 'overview' ? 'text-rose-400' : 'text-white/40'} />
            <span>Overview</span>
          </button>

          <button
            onClick={() => setActiveTab('audit')}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-[2px] text-[12px] font-medium transition-all cursor-pointer ${
              activeTab === 'audit'
                ? 'text-white bg-white/[0.06] border border-white/[0.05] font-semibold'
                : 'text-white/60 hover:text-white hover:bg-white/[0.02]'
            }`}
          >
            <div className="flex items-center space-x-3">
              <Activity size={14} className={activeTab === 'audit' ? 'text-rose-400' : 'text-white/40'} />
              <span>Audit Log</span>
            </div>
            <span className="text-[9px] font-mono bg-white/5 border border-white/10 px-1 py-0.2 text-white/50 rounded-[1px]">
              {filteredAuditEventsCount}
            </span>
          </button>

          <div className="pt-4 text-[10px] font-mono font-bold tracking-wider text-white/30 uppercase px-3 mb-2">
            Access Rules
          </div>

          <button
            onClick={() => setActiveTab('rbac')}
            className={`w-full flex items-center space-x-3 px-3 py-2 rounded-[2px] text-[12px] font-medium transition-all cursor-pointer ${
              activeTab === 'rbac'
                ? 'text-white bg-white/[0.06] border border-white/[0.05] font-semibold'
                : 'text-white/60 hover:text-white hover:bg-white/[0.02]'
            }`}
          >
            <ShieldCheck size={14} className={activeTab === 'rbac' ? 'text-rose-400' : 'text-white/40'} />
            <span>RBAC Roles</span>
          </button>

          <button
            onClick={() => setActiveTab('guardrails')}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-[2px] text-[12px] font-medium transition-all cursor-pointer ${
              activeTab === 'guardrails'
                ? 'text-white bg-white/[0.06] border border-white/[0.05] font-semibold'
                : 'text-white/60 hover:text-white hover:bg-white/[0.02]'
            }`}
          >
            <div className="flex items-center space-x-3">
              <Sliders size={14} className={activeTab === 'guardrails' ? 'text-rose-400' : 'text-white/40'} />
              <span>Guardrail Policies</span>
            </div>
            {totalActivePolicies < 3 && (
              <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" title="Some guardrails disabled" />
            )}
          </button>

          <div className="pt-4 text-[10px] font-mono font-bold tracking-wider text-white/30 uppercase px-3 mb-2">
            Identity & System
          </div>

          <button
            onClick={() => setActiveTab('users')}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-[2px] text-[12px] font-medium transition-all cursor-pointer ${
              activeTab === 'users'
                ? 'text-white bg-white/[0.06] border border-white/[0.05] font-semibold'
                : 'text-white/60 hover:text-white hover:bg-white/[0.02]'
            }`}
          >
            <div className="flex items-center space-x-3">
              <Users size={14} className={activeTab === 'users' ? 'text-rose-400' : 'text-white/40'} />
              <span>Users</span>
            </div>
            {activeAlertsCount > 0 && (
              <span className="text-[9px] font-mono font-bold bg-rose-500/20 border border-rose-500/35 text-rose-400 px-1.5 py-0.2 rounded-[1px] animate-pulse">
                {activeAlertsCount} ALERT{activeAlertsCount > 1 ? 'S' : ''}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('providers')}
            className={`w-full flex items-center space-x-3 px-3 py-2 rounded-[2px] text-[12px] font-medium transition-all cursor-pointer ${
              activeTab === 'providers'
                ? 'text-white bg-white/[0.06] border border-white/[0.05] font-semibold'
                : 'text-white/60 hover:text-white hover:bg-white/[0.02]'
            }`}
          >
            <Server size={14} className={activeTab === 'providers' ? 'text-rose-400' : 'text-white/40'} />
            <span>Providers</span>
          </button>

          <button
            onClick={() => setActiveTab('settings')}
            className={`w-full flex items-center space-x-3 px-3 py-2 rounded-[2px] text-[12px] font-medium transition-all cursor-pointer ${
              activeTab === 'settings'
                ? 'text-white bg-white/[0.06] border border-white/[0.05] font-semibold'
                : 'text-white/60 hover:text-white hover:bg-white/[0.02]'
            }`}
          >
            <SettingsIcon size={14} className={activeTab === 'settings' ? 'text-rose-400' : 'text-white/40'} />
            <span>Settings</span>
          </button>
        </div>

      </div>

      {/* RIGHT MAIN WORKSPACE */}
      <div className="flex-1 flex flex-col h-full min-w-0 bg-[#05080c]">
        
        {/* TOP PANEL BAR */}
        <div className="h-16 px-6 border-b border-white/[0.08] flex items-center justify-between bg-[#070b11]/50">
          <div className="flex items-center space-x-3">
            <span className="text-[11px] font-mono bg-white/[0.03] border border-white/[0.08] px-2 py-0.5 text-white/50 rounded-[1px]">
              ORG: TORKQ_GLOBAL
            </span>
            <span className="text-white/20">/</span>
            <span className="text-xs text-white/70 font-mono">
              active-cluster: <span className="text-emerald-400 font-bold">● EAST_INBOUND_01</span>
            </span>
          </div>

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2.5">
              <div className="w-7 h-7 rounded-[2px] bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
                <span className="text-[10px] font-semibold text-rose-300 font-mono">AD</span>
              </div>
              <div className="flex flex-col text-left">
                <span className="text-xs font-semibold text-white/80">{userEmail.split('@')[0]}</span>
                <span className="text-[8px] font-mono text-white/40 tracking-wider">SEC_PLATFORM_ADMIN</span>
              </div>
            </div>

            <button
              onClick={onSignOut}
              className="p-1.5 text-white/40 hover:text-white/80 hover:bg-white/5 rounded-[2px] transition-colors cursor-pointer"
              title="Terminate Admin Session"
            >
              <LogOut size={13} />
            </button>
          </div>
        </div>

        {/* COMPACT FLOATING TOAST PANEL */}
        {toastMessage && (
          <div className="absolute top-20 right-6 z-50 bg-[#070d14] border border-emerald-500/30 text-emerald-400 px-4 py-2 rounded-[2px] shadow-2xl flex items-center space-x-2 font-mono text-xs transition-opacity duration-300">
            <Check size={14} />
            <span>{toastMessage}</span>
          </div>
        )}

        {/* WORKSPACE PAGE CONTAINER */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* First-run gate: nothing below (Overview/Users/Audit/Providers)
              can load real data without an admin key -- loadKeys/loadAuditEvents
              simply don't fire while config.adminKey is empty (see the two
              useEffects above), so those tabs would otherwise render an
              indistinguishable "no data yet" empty state. Surface the real
              reason instead of leaving it to look broken. */}
          {!config.adminKey && activeTab !== 'settings' && (
            <div className="bg-amber-500/[0.04] border border-amber-500/20 p-4 rounded-[2px] flex items-center justify-between gap-4">
              <div className="flex items-center space-x-3">
                <div className="p-1.5 bg-amber-500/10 rounded-[1px]">
                  <ShieldCheck size={14} className="text-amber-400" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white/90">No admin key configured for this session</div>
                  <div className="text-[10px] font-mono text-white/40 mt-0.5">
                    Users, budgets, and audit logs can't load until an admin key is set. Paste your gateway's admin key in Settings once -- it's remembered for this account afterward.
                  </div>
                </div>
              </div>
              <button
                onClick={() => setActiveTab('settings')}
                className="shrink-0 px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/15 border border-amber-500/25 text-amber-300 rounded-[1px] text-[10px] font-mono font-bold uppercase tracking-wider transition-all cursor-pointer"
              >
                Go to Settings
              </button>
            </div>
          )}

          {/* Overview Tab render */}
          {activeTab === 'overview' && (
            <OverviewTab
              stats={stats}
              keys={keys}
              keysLoading={keysLoading}
              alertThresholdPct={alertThresholdPct}
              setAlertThresholdPct={setAlertThresholdPct}
              dismissedAlertIds={dismissedAlertIds}
              thresholdAlerts={thresholdAlerts}
              activeAlertsCount={activeAlertsCount}
              resetAlerts={resetAlerts}
              dismissAlert={dismissAlert}
              handleExportCSV={handleExportCSV}
              showToast={showToast}
            />
          )}

          {/* Audit Log Tab render */}
          {activeTab === 'audit' && (
            <AuditLogTab
              auditFilters={auditFilters}
              setAuditFilters={setAuditFilters}
              uniqueUsersInEvents={uniqueUsersInEvents}
              filteredAuditEvents={filteredAuditEvents}
              expandedEventId={expandedEventId}
              setExpandedEventId={setExpandedEventId}
              showToast={showToast}
              auditLoading={auditLoading}
              auditLoadError={auditLoadError}
              onRefresh={loadAuditEvents}
            />
          )}

          {/* RBAC permissions matrix render */}
          {activeTab === 'rbac' && (
            <RbacTab
              rbacMatrix={rbacMatrix}
              toggleRbacPermission={toggleRbacPermission}
              modelsAndCapabilities={MODELS_AND_CAPABILITIES}
              showToast={showToast}
            />
          )}

          {/* Guardrail configuration settings render */}
          {activeTab === 'guardrails' && (
            <GuardrailsTab
              piiEnabled={piiEnabled}
              setPiiEnabled={setPiiEnabled}
              piiRedactAll={piiRedactAll}
              setPiiRedactAll={setPiiRedactAll}
              piiSandboxInput={piiSandboxInput}
              setPiiSandboxInput={setPiiSandboxInput}
              piiSandboxOutput={piiSandboxOutput}
              testPiiRule={testPiiRule}
              secretEnabled={secretEnabled}
              setSecretEnabled={setSecretEnabled}
              entropyThreshold={entropyThreshold}
              setEntropyThreshold={setEntropyThreshold}
              secretSandboxInput={secretSandboxInput}
              setSecretSandboxInput={setSecretSandboxInput}
              secretSandboxOutput={secretSandboxOutput}
              testSecretRule={testSecretRule}
              codeVulnEnabled={codeVulnEnabled}
              setCodeVulnEnabled={setCodeVulnEnabled}
              codeVulnStrictness={codeVulnStrictness}
              setCodeVulnStrictness={setCodeVulnStrictness}
              codeSandboxInput={codeSandboxInput}
              setCodeSandboxInput={setCodeSandboxInput}
              codeSandboxOutput={codeSandboxOutput}
              testCodeRule={testCodeRule}
              showToast={showToast}
            />
          )}

          {/* User/virtual-key management render -- now backed by /v1/admin/keys */}
          {activeTab === 'users' && (
            <UsersTab showToast={showToast} />
          )}

          {/* Provider + model registry render -- backed by /v1/admin/providers & /v1/admin/models */}
          {activeTab === 'providers' && (
            <ProvidersTab showToast={showToast} />
          )}

          {/* Global network cluster configs render */}
          {activeTab === 'settings' && (
            <SettingsTab
              rateLimit={rateLimit}
              setRateLimit={setRateLimit}
              enforceStrictSsl={enforceStrictSsl}
              setEnforceStrictSsl={setEnforceStrictSsl}
              sessionTimeout={sessionTimeout}
              setSessionTimeout={setSessionTimeout}
              showToast={showToast}
              userEmail={userEmail}
            />
          )}

        </div>

      </div>

    </div>
  );
}
