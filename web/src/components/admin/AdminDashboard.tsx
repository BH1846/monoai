import React, { useState } from 'react';
import {
  LayoutDashboard,
  ShieldCheck,
  Sliders,
  Users,
  Server,
  Settings as SettingsIcon,
  ArrowLeft,
  LogOut,
  Activity,
  Check
} from 'lucide-react';
import { AdminTab, AuditEvent, UserRecord, RbacMatrix } from '../../types';

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
const INITIAL_AUDIT_EVENTS: AuditEvent[] = [
  {
    id: 'evt-101',
    timestamp: '2026-06-26T08:45:12Z',
    decision: 'BLOCKED',
    rule: 'SECRET_SCAN',
    user: 'rahulbalaskandan1511@gmail.com',
    model: 'gemini-3.5-flash',
    detail: 'DLP high-entropy matching triggered for "AWS_SECRET_ACCESS_KEY" in database connection query.'
  },
  {
    id: 'evt-102',
    timestamp: '2026-06-26T08:40:05Z',
    decision: 'REDACTED',
    rule: 'PII_SCAN',
    user: 'sjenkins@monoai.io',
    model: 'gpt-4o',
    detail: 'Masked Social Security Number (SSN: ***-**-****) and outbound email from marketing pitch input.'
  },
  {
    id: 'evt-103',
    timestamp: '2026-06-26T08:31:42Z',
    decision: 'ALLOWED',
    rule: 'RBAC',
    user: 'alex_rivera@monoai.io',
    model: 'claude-3-5-sonnet',
    detail: 'Successful routed proxy through Auto-Routing Gateway with valid standard developer scope.'
  },
  {
    id: 'evt-104',
    timestamp: '2026-06-26T08:22:15Z',
    decision: 'BLOCKED',
    rule: 'CODE_VULN',
    user: 'dchen@monoai.io',
    model: 'gemini-1.5-pro',
    detail: 'Neutralized SQL injection pattern "UNION SELECT username, password FROM users" in database optimization script.'
  },
  {
    id: 'evt-105',
    timestamp: '2026-06-26T07:54:33Z',
    decision: 'REDACTED',
    rule: 'PII_SCAN',
    user: 'customer_support_api',
    model: 'gemini-3.5-flash',
    detail: 'Automatically redacted customer phone numbers (+1 555-0192) inside high-volume log inputs.'
  },
  {
    id: 'evt-106',
    timestamp: '2026-06-26T07:11:02Z',
    decision: 'ALLOWED',
    rule: 'SECRET_SCAN',
    user: 'rahulbalaskandan1511@gmail.com',
    model: 'gemini-3.5-flash',
    detail: 'Clear entropy scan. Request successfully dispatched to dynamic inference pool.'
  },
  {
    id: 'evt-107',
    timestamp: '2026-06-26T06:40:59Z',
    decision: 'BLOCKED',
    rule: 'RBAC',
    user: 'guest_sandbox',
    model: 'o1-pro',
    detail: 'Access denied. Guest scope does not permit execution of reasoning-trace high-fidelity models (o1-pro).'
  },
  {
    id: 'evt-108',
    timestamp: '2026-06-26T05:12:14Z',
    decision: 'REDACTED',
    rule: 'PII_SCAN',
    user: 'sjenkins@monoai.io',
    model: 'gpt-4o',
    detail: 'Masked outbound personal physical address fields from validation payload.'
  },
  {
    id: 'evt-109',
    timestamp: '2026-06-26T04:30:11Z',
    decision: 'ALLOWED',
    rule: 'RBAC',
    user: 'alex_rivera@monoai.io',
    model: 'gemini-3.5-flash',
    detail: 'Cleared standard routing verification for local workspace model dispatch.'
  },
  {
    id: 'evt-110',
    timestamp: '2026-06-26T03:02:44Z',
    decision: 'BLOCKED',
    rule: 'SECRET_SCAN',
    user: 'ci_pipeline_bot',
    model: 'gemini-3.5-flash',
    detail: 'DLP scanner matched high-entropy Stripe secret key "sk_test_..." in configuration deployment test.'
  }
];

const INITIAL_USERS: UserRecord[] = [
  {
    id: 'usr-1',
    name: 'Rahul Balaskandan',
    email: 'rahulbalaskandan1511@gmail.com',
    role: 'Administrator',
    lastActive: '2026-06-26 08:50:22',
    status: 'active',
    totalCost: 12.45,
    costLimit: 50.00,
    inputTokens: 412000,
    outputTokens: 184000
  },
  {
    id: 'usr-2',
    name: 'Sarah Jenkins',
    email: 'sjenkins@monoai.io',
    role: 'Compliance Officer',
    lastActive: '2026-06-26 08:41:00',
    status: 'active',
    totalCost: 8.12,
    costLimit: 25.00,
    inputTokens: 250000,
    outputTokens: 110000
  },
  {
    id: 'usr-3',
    name: 'Alex Rivera',
    email: 'alex_rivera@monoai.io',
    role: 'Developer',
    lastActive: '2026-06-26 08:32:15',
    status: 'active',
    totalCost: 19.95,
    costLimit: 20.00,
    inputTokens: 680000,
    outputTokens: 310000
  },
  {
    id: 'usr-4',
    name: 'David Chen',
    email: 'dchen@monoai.io',
    role: 'Developer',
    lastActive: '2026-06-26 08:24:45',
    status: 'active',
    totalCost: 35.60,
    costLimit: 30.00,
    inputTokens: 1240000,
    outputTokens: 520000
  },
  {
    id: 'usr-5',
    name: 'CI Integration Bot',
    email: 'ci_pipeline_bot',
    role: 'API Service Account',
    lastActive: '2026-06-26 03:02:44',
    status: 'active',
    totalCost: 4.88,
    costLimit: 100.00,
    inputTokens: 180000,
    outputTokens: 95000
  },
  {
    id: 'usr-6',
    name: 'Guest Sandbox',
    email: 'guest_sandbox',
    role: 'Guest Observer',
    lastActive: '2026-06-26 06:40:59',
    status: 'disabled',
    totalCost: 0.00,
    costLimit: 10.00,
    inputTokens: 0,
    outputTokens: 0
  }
];

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

  // Unified State
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>(INITIAL_AUDIT_EVENTS);
  const [users, setUsers] = useState<UserRecord[]>(INITIAL_USERS);
  const [rbacMatrix, setRbacMatrix] = useState<RbacMatrix>(INITIAL_RBAC_MATRIX);

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

  // Derived budget threshold alerts based on current state and settings
  const thresholdAlerts = users.map(u => {
    const pct = (u.costLimit || 0) > 0 ? ((u.totalCost || 0) / (u.costLimit || 0)) * 100 : 0;
    const isExceeded = (u.costLimit || 0) > 0 && pct >= alertThresholdPct;
    if (isExceeded) {
      return {
        userId: u.id,
        user: u,
        percentage: pct,
        isBreach: pct >= 100
      };
    }
    return null;
  }).filter((x): x is NonNullable<typeof x> => x !== null);

  const activeAlertsCount = thresholdAlerts.filter(a => !dismissedAlertIds.includes(a.userId)).length;

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

  const toggleUserStatus = (userId: string) => {
    setUsers(prev => prev.map(u => {
      if (u.id === userId) {
        const nextStatus = u.status === 'active' ? 'disabled' : 'active';
        showToast(`User status for ${u.email} set to ${nextStatus.toUpperCase()}`);
        return { ...u, status: nextStatus };
      }
      return u;
    }));
  };

  const updateUserCostLimit = (userId: string, limit: number) => {
    setUsers(prev => prev.map(u => {
      if (u.id === userId) {
        showToast(`Cost limit updated for ${u.name} to $${limit.toFixed(2)}`);
        return { ...u, costLimit: limit };
      }
      return u;
    }));
  };

  const resetUserCost = (userId: string) => {
    setUsers(prev => prev.map(u => {
      if (u.id === userId) {
        showToast(`Cumulative cost accumulator reset for ${u.name}`);
        setDismissedAlertIds(prevD => prevD.filter(id => id !== userId));
        return { ...u, totalCost: 0, inputTokens: 0, outputTokens: 0 };
      }
      return u;
    }));
  };

  const simulateTrafficForUser = (userId: string) => {
    const additionalInput = Math.floor(Math.random() * 95000) + 15000;
    const additionalOutput = Math.floor(Math.random() * 45000) + 5000;
    const additionalCost = parseFloat(((additionalInput * 0.00001) + (additionalOutput * 0.000025)).toFixed(2));

    setUsers(prev => prev.map(u => {
      if (u.id === userId) {
        const nextInput = (u.inputTokens || 0) + additionalInput;
        const nextOutput = (u.outputTokens || 0) + additionalOutput;
        const nextCost = parseFloat(((u.totalCost || 0) + additionalCost).toFixed(2));
        
        const prevPct = (u.costLimit || 0) > 0 ? ((u.totalCost || 0) / (u.costLimit || 0)) * 100 : 0;
        const nextPct = (u.costLimit || 0) > 0 ? (nextCost / (u.costLimit || 0)) * 100 : 0;

        if (prevPct < 100 && nextPct >= 100) {
          setDismissedAlertIds(prevD => prevD.filter(id => id !== userId));
        }

        if (u.costLimit > 0) {
          if (prevPct < alertThresholdPct && nextPct >= alertThresholdPct && nextPct < 100) {
            showToast(`⚠️ WARNING threshold crossed for ${u.name}! Used ${nextPct.toFixed(1)}% of budget.`);
          } else if (prevPct < 100 && nextPct >= 100) {
            showToast(`🚨 CRITICAL BUDGET BREACH: ${u.name} has exceeded 100% of cost limit ($${nextCost.toFixed(2)} / $${u.costLimit.toFixed(2)})!`);
          } else {
            showToast(`Traffic simulated for ${u.name}: +$${additionalCost.toFixed(2)} (${(additionalInput + additionalOutput).toLocaleString()} tokens)`);
          }
        } else {
          showToast(`Traffic simulated for ${u.name}: +$${additionalCost.toFixed(2)}`);
        }

        return {
          ...u,
          inputTokens: nextInput,
          outputTokens: nextOutput,
          totalCost: nextCost,
          lastActive: new Date().toISOString().replace('T', ' ').substring(0, 19)
        };
      }
      return u;
    }));
  };

  const dismissAlert = (userId: string) => {
    setDismissedAlertIds(prev => [...prev, userId]);
    showToast(`Alert for user dismissed in this session`);
  };

  const resetAlerts = () => {
    setDismissedAlertIds([]);
    showToast(`All budget threshold alert states refreshed`);
  };

  const handleExportCSV = () => {
    const headers = [
      'User ID',
      'Name',
      'Email',
      'Role',
      'Status',
      'Input Tokens',
      'Output Tokens',
      'Total Tokens',
      'Total Cost (USD)',
      'Cost Limit (USD)',
      'Quota Used (%)',
      'Limit Breach Status',
      'Last Active'
    ];

    const rows = users.map(u => {
      const totalTokens = (u.inputTokens || 0) + (u.outputTokens || 0);
      const quotaPct = (u.costLimit || 0) > 0 ? ((u.totalCost || 0) / (u.costLimit || 0)) * 100 : 0;
      const isBreached = (u.costLimit || 0) > 0 && (u.totalCost || 0) >= (u.costLimit || 0) ? 'BREACHED' : 'OK';
      
      const escapedName = u.name ? u.name.replace(/"/g, '""') : '';
      const escapedEmail = u.email ? u.email.replace(/"/g, '""') : '';
      const escapedRole = u.role ? u.role.replace(/"/g, '""') : '';

      return [
        u.id,
        `"${escapedName}"`,
        `"${escapedEmail}"`,
        `"${escapedRole}"`,
        u.status,
        u.inputTokens || 0,
        u.outputTokens || 0,
        totalTokens,
        (u.totalCost || 0).toFixed(2),
        (u.costLimit || 0).toFixed(2),
        `${quotaPct.toFixed(1)}%`,
        isBreached,
        u.lastActive
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
              M
            </div>
            <div>
              <span className="font-sans text-[13px] tracking-widest text-white/90 font-bold uppercase">
                MonoAI
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

        {/* Return Button */}
        <div className="p-3 border-t border-white/[0.08] bg-[#05080d]/80 space-y-2">
          <button
            onClick={onBackToWorkspace}
            className="w-full flex items-center justify-center space-x-2 px-3 py-2 rounded-[2px] border border-rose-500/20 bg-rose-500/5 hover:bg-rose-500/10 text-rose-300 text-[11px] font-mono tracking-tight transition-colors cursor-pointer"
          >
            <ArrowLeft size={12} />
            <span>RETURN TO CHATS</span>
          </button>
        </div>
      </div>

      {/* RIGHT MAIN WORKSPACE */}
      <div className="flex-1 flex flex-col h-full min-w-0 bg-[#05080c]">
        
        {/* TOP PANEL BAR */}
        <div className="h-16 px-6 border-b border-white/[0.08] flex items-center justify-between bg-[#070b11]/50">
          <div className="flex items-center space-x-3">
            <span className="text-[11px] font-mono bg-white/[0.03] border border-white/[0.08] px-2 py-0.5 text-white/50 rounded-[1px]">
              ORG: MONOAI_GLOBAL
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
          
          {/* Overview Tab render */}
          {activeTab === 'overview' && (
            <OverviewTab
              stats={stats}
              users={users}
              alertThresholdPct={alertThresholdPct}
              setAlertThresholdPct={setAlertThresholdPct}
              dismissedAlertIds={dismissedAlertIds}
              thresholdAlerts={thresholdAlerts}
              activeAlertsCount={activeAlertsCount}
              resetAlerts={resetAlerts}
              simulateTrafficForUser={simulateTrafficForUser}
              dismissAlert={dismissAlert}
              resetUserCost={resetUserCost}
              handleExportCSV={handleExportCSV}
              updateUserCostLimit={updateUserCostLimit}
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
            />
          )}

          {/* RBAC permissions matrix render */}
          {activeTab === 'rbac' && (
            <RbacTab
              rbacMatrix={rbacMatrix}
              toggleRbacPermission={toggleRbacPermission}
              users={users}
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
