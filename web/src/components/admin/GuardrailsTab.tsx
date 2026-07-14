import React from 'react';
import { Sliders, Play } from 'lucide-react';

interface GuardrailsTabProps {
  piiEnabled: boolean;
  setPiiEnabled: (val: boolean) => void;
  piiRedactAll: boolean;
  setPiiRedactAll: (val: boolean) => void;
  piiSandboxInput: string;
  setPiiSandboxInput: (val: string) => void;
  piiSandboxOutput: string;
  testPiiRule: () => void;

  secretEnabled: boolean;
  setSecretEnabled: (val: boolean) => void;
  entropyThreshold: number;
  setEntropyThreshold: (val: number) => void;
  secretSandboxInput: string;
  setSecretSandboxInput: (val: string) => void;
  secretSandboxOutput: string;
  testSecretRule: () => void;

  codeVulnEnabled: boolean;
  setCodeVulnEnabled: (val: boolean) => void;
  codeVulnStrictness: string;
  setCodeVulnStrictness: (val: string) => void;
  codeSandboxInput: string;
  setCodeSandboxInput: (val: string) => void;
  codeSandboxOutput: string;
  testCodeRule: () => void;

  showToast: (msg: string) => void;
}

export default function GuardrailsTab({
  piiEnabled,
  setPiiEnabled,
  piiRedactAll,
  setPiiRedactAll,
  piiSandboxInput,
  setPiiSandboxInput,
  piiSandboxOutput,
  testPiiRule,

  secretEnabled,
  setSecretEnabled,
  entropyThreshold,
  setEntropyThreshold,
  secretSandboxInput,
  setSecretSandboxInput,
  secretSandboxOutput,
  testSecretRule,

  codeVulnEnabled,
  setCodeVulnEnabled,
  codeVulnStrictness,
  setCodeVulnStrictness,
  codeSandboxInput,
  setCodeSandboxInput,
  codeSandboxOutput,
  testCodeRule,

  showToast
}: GuardrailsTabProps) {
  return (
    <div className="space-y-6">
      
      {/* COMPACT EXPLANATION */}
      <div className="bg-[#070c14] border border-white/[0.06] p-4 rounded-[2px] space-y-1">
        <div className="flex items-center space-x-2">
          <Sliders size={15} className="text-rose-400" />
          <span className="text-xs font-mono font-bold uppercase text-white/90">Pre-Flight Guardrail Policies</span>
        </div>
        <p className="text-xs text-white/45 leading-relaxed">
          Torkq scans every incoming request before dispatching it to external LLMs. Adjust scan profiles and verify detection models dynamically below.
        </p>
      </div>

      {/* THREE MAIN SCANNER POLICIES */}
      <div className="grid grid-cols-1 gap-6">
        
        {/* 1. PII SCANNER */}
        <div className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-hidden">
          <div className="p-4 border-b border-white/[0.08] bg-white/[0.01] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center space-x-3">
              <div className={`w-2 h-2 rounded-full ${piiEnabled ? 'bg-emerald-400' : 'bg-rose-500'}`} />
              <div>
                <span className="text-xs font-mono font-bold text-white/90 uppercase">1. PII Redaction Filter (Pattern Classifiers)</span>
                <span className="block text-[10px] text-white/40">Scans for and sanitizes sensitive identifiers (SSN, emails, phone numbers)</span>
              </div>
            </div>
            {/* Compact Toggle */}
            <button
              onClick={() => {
                setPiiEnabled(!piiEnabled);
                showToast(`PII Redaction Filter toggled ${!piiEnabled ? 'ON' : 'OFF'}`);
              }}
              className={`text-[10px] font-mono px-3 py-1 rounded-[1px] border transition-colors cursor-pointer ${
                piiEnabled
                  ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                  : 'bg-white/5 border-white/[0.08] text-white/40'
              }`}
            >
              {piiEnabled ? 'FILTER_STATUS: ACTIVE' : 'FILTER_STATUS: COMPROMISED/OFF'}
            </button>
          </div>

          <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Configuration column */}
            <div className="space-y-4">
              <div className="text-[10px] font-mono tracking-wider text-white/30 uppercase">Policy Parameters</div>
              
              <div className="flex items-center justify-between border-b border-white/5 pb-2">
                <span className="text-xs text-white/80">PII Masking Method</span>
                <span className="text-xs font-mono text-indigo-400">Cryptographic redacts [REDACTED_REF]</span>
              </div>

              <div className="flex items-center justify-between border-b border-white/5 pb-2">
                <span className="text-xs text-white/80">Redact All Identifiers</span>
                <button
                  onClick={() => setPiiRedactAll(!piiRedactAll)}
                  className={`w-8 h-4 rounded-full transition-colors relative cursor-pointer ${piiRedactAll ? 'bg-indigo-500' : 'bg-white/10'}`}
                >
                  <span className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all ${piiRedactAll ? 'left-4.5' : 'left-0.5'}`} />
                </button>
              </div>

              <div className="text-[10px] text-white/30 mt-2 font-mono">
                Active classifiers: EN_US_SSN, INT_EMAIL_CLASSIFIER, INT_PHONE_FORMATS, INT_CREDIT_CARD.
              </div>
            </div>

            {/* Interactive Sandbox Test column */}
            <div className="bg-[#05080c] border border-white/[0.06] p-4 rounded-[2px] space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-white/40 uppercase">DLP Sandbox Verification</span>
                <button
                  onClick={testPiiRule}
                  className="flex items-center space-x-1 px-2.5 py-1 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 rounded-[1px] text-[10px] text-indigo-300 font-mono transition-colors cursor-pointer"
                >
                  <Play size={10} />
                  <span>TEST PAYLOAD</span>
                </button>
              </div>

              <textarea
                value={piiSandboxInput}
                onChange={(e) => setPiiSandboxInput(e.target.value)}
                className="w-full bg-white/[0.01] hover:bg-white/[0.03] border border-white/[0.08] focus:border-rose-500/30 p-2 text-xs font-mono rounded-[1px] focus:outline-none focus:ring-0 text-white/80"
                rows={3}
                placeholder="Paste testing string containing PII..."
              />

              {piiSandboxOutput && (
                <div className="space-y-1">
                  <span className="text-[9px] font-mono text-emerald-400">GATEWAY PARSING RESULT:</span>
                  <div className="bg-[#030509] p-2 border border-white/[0.06] rounded-[1px] font-mono text-xs text-emerald-300/90 whitespace-pre-wrap leading-relaxed">
                    {piiSandboxOutput}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>


        {/* 2. SECRET SCANNER */}
        <div className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-hidden">
          <div className="p-4 border-b border-white/[0.08] bg-white/[0.01] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center space-x-3">
              <div className={`w-2 h-2 rounded-full ${secretEnabled ? 'bg-emerald-400' : 'bg-rose-500'}`} />
              <div>
                <span className="text-xs font-mono font-bold text-white/90 uppercase">2. Entropy Secret Key Scanner (Entropy DLP)</span>
                <span className="block text-[10px] text-white/40">Guards outbound channels from leakages of raw config parameters and API keys</span>
              </div>
            </div>
            {/* Compact Toggle */}
            <button
              onClick={() => {
                setSecretEnabled(!secretEnabled);
                showToast(`Secret Key Scanner toggled ${!secretEnabled ? 'ON' : 'OFF'}`);
              }}
              className={`text-[10px] font-mono px-3 py-1 rounded-[1px] border transition-colors cursor-pointer ${
                secretEnabled
                  ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                  : 'bg-white/5 border-white/[0.08] text-white/40'
              }`}
            >
              {secretEnabled ? 'FILTER_STATUS: ACTIVE' : 'FILTER_STATUS: COMPROMISED/OFF'}
            </button>
          </div>

          <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Configuration column */}
            <div className="space-y-4">
              <div className="text-[10px] font-mono tracking-wider text-white/30 uppercase">Policy Parameters</div>
              
              <div className="space-y-2 border-b border-white/5 pb-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-white/80">Shannon Entropy Limit</span>
                  <span className="text-xs font-mono font-bold text-amber-400">{entropyThreshold} bits</span>
                </div>
                <input
                  type="range"
                  min="3.0"
                  max="6.5"
                  step="0.1"
                  value={entropyThreshold}
                  onChange={(e) => setEntropyThreshold(parseFloat(e.target.value))}
                  className="w-full accent-amber-500 h-1 bg-white/10 rounded-lg appearance-none cursor-pointer"
                />
                <div className="flex justify-between text-[8px] font-mono text-white/30">
                  <span>3.0 (Strict / False Positives)</span>
                  <span>6.5 (Lenient)</span>
                </div>
              </div>

              <div className="flex items-center justify-between border-b border-white/5 pb-2">
                <span className="text-xs text-white/80">Severity Action</span>
                <span className="text-xs font-mono text-rose-400 uppercase font-bold">TERMINATE_PROXY</span>
              </div>
            </div>

            {/* Interactive Sandbox Test column */}
            <div className="bg-[#05080c] border border-white/[0.06] p-4 rounded-[2px] space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-white/40 uppercase">Secret Scanner Sandbox</span>
                <button
                  onClick={testSecretRule}
                  className="flex items-center space-x-1 px-2.5 py-1 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 rounded-[1px] text-[10px] text-indigo-300 font-mono transition-colors cursor-pointer"
                >
                  <Play size={10} />
                  <span>TEST PAYLOAD</span>
                </button>
              </div>

              <textarea
                value={secretSandboxInput}
                onChange={(e) => setSecretSandboxInput(e.target.value)}
                className="w-full bg-white/[0.01] hover:bg-white/[0.03] border border-white/[0.08] focus:border-rose-500/30 p-2 text-xs font-mono rounded-[1px] focus:outline-none focus:ring-0 text-white/80"
                rows={3}
                placeholder="Paste config or keys to scan entropy..."
              />

              {secretSandboxOutput && (
                <div className="space-y-1">
                  <span className="text-[9px] font-mono text-amber-400">ENTROPY COMPILER RESPONSE:</span>
                  <div className={`bg-[#030509] p-2 border border-white/[0.06] rounded-[1px] font-mono text-xs whitespace-pre-wrap leading-relaxed ${
                    secretSandboxOutput.includes('BLOCKED') ? 'text-rose-300/90' : 'text-emerald-300/90'
                  }`}>
                    {secretSandboxOutput}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>


        {/* 3. CODE VULNERABILITY SCANNER */}
        <div className="bg-[#070b11] border border-white/[0.08] rounded-[2px] overflow-hidden">
          <div className="p-4 border-b border-white/[0.08] bg-white/[0.01] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center space-x-3">
              <div className={`w-2 h-2 rounded-full ${codeVulnEnabled ? 'bg-emerald-400' : 'bg-rose-500'}`} />
              <div>
                <span className="text-xs font-mono font-bold text-white/90 uppercase">3. Injection and Injection Neutralizer</span>
                <span className="block text-[10px] text-white/40">Intercepts SQL injection, prototype pollution, and terminal commands injection</span>
              </div>
            </div>
            {/* Compact Toggle */}
            <button
              onClick={() => {
                setCodeVulnEnabled(!codeVulnEnabled);
                showToast(`Vulnerability Scanner toggled ${!codeVulnEnabled ? 'ON' : 'OFF'}`);
              }}
              className={`text-[10px] font-mono px-3 py-1 rounded-[1px] border transition-colors cursor-pointer ${
                codeVulnEnabled
                  ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                  : 'bg-white/5 border-white/[0.08] text-white/40'
              }`}
            >
              {codeVulnEnabled ? 'FILTER_STATUS: ACTIVE' : 'FILTER_STATUS: COMPROMISED/OFF'}
            </button>
          </div>

          <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Configuration column */}
            <div className="space-y-4">
              <div className="text-[10px] font-mono tracking-wider text-white/30 uppercase">Policy Parameters</div>
              
              <div className="flex items-center justify-between border-b border-white/5 pb-2">
                <span className="text-xs text-white/80">Scanning Profiles</span>
                <div className="flex space-x-1">
                  {['Lenient', 'Muted', 'Strict'].map(level => (
                    <button
                      key={level}
                      onClick={() => {
                        setCodeVulnStrictness(level);
                        showToast(`Vulnerability Strictness level set to ${level}`);
                      }}
                      className={`text-[9px] font-mono px-2 py-0.5 rounded-[1px] border cursor-pointer ${
                        codeVulnStrictness === level
                          ? 'bg-indigo-500/10 border-indigo-500/40 text-indigo-400 font-bold'
                          : 'bg-white/5 border-white/5 text-white/30'
                      }`}
                    >
                      {level.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between border-b border-white/5 pb-2">
                <span className="text-xs text-white/80">Dynamic Override Target</span>
                <span className="text-xs font-mono text-emerald-400 uppercase font-bold">REPLACE_WITH_BINDINGS</span>
              </div>
            </div>

            {/* Interactive Sandbox Test column */}
            <div className="bg-[#05080c] border border-white/[0.06] p-4 rounded-[2px] space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-white/40 uppercase">Injection Sandbox Testing</span>
                <button
                  onClick={testCodeRule}
                  className="flex items-center space-x-1 px-2.5 py-1 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 rounded-[1px] text-[10px] text-indigo-300 font-mono transition-colors cursor-pointer"
                >
                  <Play size={10} />
                  <span>TEST PAYLOAD</span>
                </button>
              </div>

              <textarea
                value={codeSandboxInput}
                onChange={(e) => setCodeSandboxInput(e.target.value)}
                className="w-full bg-white/[0.01] hover:bg-white/[0.03] border border-white/[0.08] focus:border-rose-500/30 p-2 text-xs font-mono rounded-[1px] focus:outline-none focus:ring-0 text-white/80"
                rows={3}
                placeholder="Paste code containing SQL commands or bash injections..."
              />

              {codeSandboxOutput && (
                <div className="space-y-1">
                  <span className="text-[9px] font-mono text-indigo-400">COMPLEX SCANS ANALYZER:</span>
                  <div className={`bg-[#030509] p-2 border border-white/[0.06] rounded-[1px] font-mono text-xs whitespace-pre-wrap leading-relaxed ${
                    codeSandboxOutput.includes('MITIGATED') ? 'text-amber-300/90' : 'text-emerald-300/90'
                  }`}>
                    {codeSandboxOutput}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

      </div>

    </div>
  );
}
