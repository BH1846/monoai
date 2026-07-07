import React, { useState } from 'react';
import { Shield, Eye, EyeOff } from 'lucide-react';

interface SignInProps {
  onSignIn: (email: string, role: 'admin' | 'user') => void;
}

export default function SignIn({ onSignIn }: SignInProps) {
  const [loginTab, setLoginTab] = useState<'user' | 'admin'>('user');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const inputEmail = email.trim();
    const inputPass = password.trim();

    // Defensive input check
    if (!inputEmail || !inputPass) {
      setError('Incorrect email or password.');
      return;
    }

    setIsSubmitting(true);

    // Simulate precise enterprise network delay
    setTimeout(() => {
      const normalizedEmail = inputEmail.toLowerCase();
      
      if (loginTab === 'admin') {
        // Dedicated admin credentials
        if (
          (normalizedEmail === 'admin@mono.ai' && inputPass === 'admin') ||
          (normalizedEmail === 'engineer@mono.ai' && inputPass === 'governance2026')
        ) {
          onSignIn(inputEmail, 'admin');
        } else {
          setError('Invalid administrator credentials or role clearance failed.');
        }
      } else {
        // Standard user credentials
        if (
          (normalizedEmail === 'user' && inputPass === 'user') ||
          (normalizedEmail === 'dev' && inputPass === 'dev')
        ) {
          onSignIn(inputEmail, 'user');
        } else {
          setError('Invalid user credentials or gateway access denied.');
        }
      }
      setIsSubmitting(false);
    }, 600);
  };

  return (
    <div className="min-h-screen w-screen bg-[#0A0E14] text-white flex flex-col font-sans overflow-hidden">

      {/* Sign-In Form Area, centered */}
      <div className="w-full flex flex-col justify-between p-8 lg:p-12 xl:p-16 bg-[#0A0E14] z-10 min-h-screen">

        {/* Top brand signature */}
        <div className="flex items-center space-x-2.5 select-none animate-fadeIn">
          <div className="w-6 h-6 bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center rounded-[2px]">
            <Shield size={12} className="text-indigo-400" />
          </div>
          <span className="text-[13px] font-mono tracking-widest font-bold text-white/90">MONOAI</span>
          <span className="text-[9px] font-mono bg-white/[0.04] border border-white/10 px-1.5 py-0.5 rounded-[1px] text-white/40 tracking-wider">GATEWAY</span>
        </div>

        {/* Center centered form block */}
        <div className="my-auto py-12 md:py-0 flex flex-col justify-center max-w-[360px] w-full mx-auto animate-fadeIn" style={{ animationDelay: '50ms' }}>
          
          <div className="space-y-2 mb-6">
            <h1 className="text-xl font-medium tracking-tight text-white select-none">
              Sign in to MonoAI
            </h1>
            <p className="text-xs text-white/40 leading-relaxed select-none">
              {loginTab === 'admin' 
                ? 'Accessing secure out-of-band security control plane console.' 
                : 'Accessing the model inference and proxy gateway portal.'}
            </p>
          </div>

          {/* Secure Partitioned Dual-Tab Login */}
          <div className="grid grid-cols-2 gap-1 bg-[#0c121a] p-1 border border-white/[0.06] rounded-[2px] mb-6">
            <button
              type="button"
              onClick={() => {
                setLoginTab('user');
                setEmail('');
                setPassword('');
                setError(null);
              }}
              className={`py-1.5 text-[10px] font-mono tracking-wider transition-all rounded-[1px] font-bold ${
                loginTab === 'user'
                  ? 'bg-white/10 text-white border border-white/10 shadow'
                  : 'text-white/40 hover:text-white/70'
              }`}
            >
              USER PORTAL
            </button>
            <button
              type="button"
              onClick={() => {
                setLoginTab('admin');
                setEmail('');
                setPassword('');
                setError(null);
              }}
              className={`py-1.5 text-[10px] font-mono tracking-wider transition-all rounded-[1px] font-bold ${
                loginTab === 'admin'
                  ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20 shadow'
                  : 'text-white/40 hover:text-white/70'
              }`}
            >
              ADMIN CONSOLE
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div 
                className="p-3 bg-red-950/25 border border-red-500/30 text-red-400 text-xs font-mono rounded-[2px] leading-relaxed flex items-start space-x-2 animate-fadeIn"
                id="signin-error"
              >
                <span className="shrink-0 text-red-500">■</span>
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-white/60 select-none">
                {loginTab === 'admin' ? 'Administrator Email' : 'Operator Username'}
              </label>
              <input
                id="email-field"
                type="text"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (error) setError(null);
                }}
                disabled={isSubmitting}
                placeholder={loginTab === 'admin' ? 'admin@mono.ai' : 'user'}
                className="w-full px-3 py-2 bg-[#0c121a]/60 border border-white/[0.08] rounded-[2px] text-xs text-white/90 placeholder-white/20 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/50 transition-all font-mono"
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <label className="block text-xs font-medium text-white/60 select-none">
                  Security Passkey
                </label>
              </div>
              <div className="relative">
                <input
                  id="password-field"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    if (error) setError(null);
                  }}
                  disabled={isSubmitting}
                  placeholder="••••••••••••"
                  className="w-full pl-3 pr-9 py-2 bg-[#0c121a]/60 border border-white/[0.08] rounded-[2px] text-xs text-white/90 placeholder-white/20 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/50 transition-all font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-all cursor-pointer p-0.5"
                  title={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
              </div>
            </div>

            <button
              id="signin-btn"
              type="submit"
              disabled={isSubmitting}
              className={`w-full py-2 font-medium text-xs rounded-[2px] hover:shadow-lg focus:outline-none focus:ring-1 transition-all cursor-pointer select-none ${
                loginTab === 'admin'
                  ? 'bg-rose-500 hover:bg-rose-400 text-white focus:ring-rose-400'
                  : 'bg-white hover:bg-white/95 text-[#0A0E14] focus:ring-indigo-500'
              } disabled:bg-white/20 disabled:text-white/40 disabled:cursor-not-allowed`}
            >
              {isSubmitting 
                ? (loginTab === 'admin' ? 'Authorizing admin token...' : 'Verifying gateway node...') 
                : (loginTab === 'admin' ? 'Access Control Plane' : 'Connect to Gateway')}
            </button>
          </form>

          {/* Dynamic helper card for current credentials */}
          <div className="mt-6 pt-5 border-t border-white/[0.03] text-[10px] font-mono text-white/30 space-y-2 select-none">
            <span className="text-indigo-400 font-semibold block uppercase tracking-wider">
              {loginTab === 'admin' ? 'Admin Clearances Available:' : 'User Gateway Credentials:'}
            </span>
            {loginTab === 'admin' ? (
              <div className="space-y-1 bg-rose-500/5 border border-rose-500/10 p-2 rounded-[1px]">
                <div>Operator: <strong className="text-rose-300 font-bold select-all">admin@mono.ai</strong></div>
                <div>Passkey: <strong className="text-white/70">admin</strong></div>
                <div className="pt-1.5 mt-1 border-t border-white/5">Operator: <strong className="text-rose-300 font-bold select-all">engineer@mono.ai</strong></div>
                <div>Passkey: <strong className="text-white/70">governance2026</strong></div>
              </div>
            ) : (
              <div className="space-y-1 bg-white/[0.02] border border-white/5 p-2 rounded-[1px]">
                <div>Identity: <strong className="text-indigo-300 font-bold select-all">user</strong></div>
                <div>Passkey: <strong className="text-white/70">user</strong></div>
                <div className="pt-1.5 mt-1 border-t border-white/5">Identity: <strong className="text-indigo-300 font-bold select-all">dev</strong></div>
                <div>Passkey: <strong className="text-white/70">dev</strong></div>
              </div>
            )}
          </div>

        </div>

        {/* Footer Area with plain enterprise microcopy */}
        <div className="pt-8 text-[11px] text-white/30 font-sans border-t border-white/[0.02] select-none animate-fadeIn" style={{ animationDelay: '100ms' }}>
          <span>Need access? </span>
          <a href="#contact" className="text-indigo-400 hover:text-indigo-300 hover:underline transition-all font-medium">
            Contact your administrator
          </a>
        </div>

      </div>

    </div>
  );
}
