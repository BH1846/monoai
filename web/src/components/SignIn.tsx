import React, { useState } from 'react';
import { Shield, Eye, EyeOff } from 'lucide-react';
import { useGateway } from '../context/GatewayContext';

interface SignInProps {
  onSignIn: (email: string, role: 'admin' | 'user') => void;
}

export default function SignIn({ onSignIn }: SignInProps) {
  const { registerUser, loginUser } = useGateway();
  const [loginTab, setLoginTab] = useState<'user' | 'admin'>('user');
  const [userMode, setUserMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const resetFields = () => {
    setEmail('');
    setPassword('');
    setConfirmPassword('');
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const inputEmail = email.trim();
    const inputPass = password.trim();

    if (!inputEmail || !inputPass) {
      setError('Incorrect email or password.');
      return;
    }

    if (loginTab === 'admin') {
      setIsSubmitting(true);
      // Dedicated admin credentials -- single shared operator secret, not a
      // per-admin account system (see gateway/auth/admin_account_store.py).
      setTimeout(() => {
        const normalizedEmail = inputEmail.toLowerCase();
        if (
          (normalizedEmail === 'admin@mono.ai' && inputPass === 'admin') ||
          (normalizedEmail === 'engineer@mono.ai' && inputPass === 'governance2026')
        ) {
          onSignIn(inputEmail, 'admin');
        } else {
          setError('Invalid administrator credentials or role clearance failed.');
        }
        setIsSubmitting(false);
      }, 600);
      return;
    }

    // Real user accounts: POST /v1/auth/register or /v1/auth/login (see
    // gateway/api/auth.py). Registering auto-creates a virtual key for the
    // new account, and both paths hand it back so useGateway()'s
    // registerUser/loginUser can populate the session immediately --
    // signing up is enough to start chatting, no admin step required.
    if (userMode === 'register' && inputPass !== confirmPassword.trim()) {
      setError('Passwords do not match.');
      return;
    }
    if (userMode === 'register' && inputPass.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setIsSubmitting(true);
    const result = userMode === 'register'
      ? await registerUser(inputEmail, inputPass)
      : await loginUser(inputEmail, inputPass);
    setIsSubmitting(false);

    if (result.status === 'ok') {
      onSignIn(result.email, 'user');
    } else {
      setError(result.error);
    }
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
          <span className="text-[13px] font-mono tracking-widest font-bold text-white/90">TORKQ</span>
          <span className="text-[9px] font-mono bg-white/[0.04] border border-white/10 px-1.5 py-0.5 rounded-[1px] text-white/40 tracking-wider">GATEWAY</span>
        </div>

        {/* Center centered form block */}
        <div className="my-auto py-12 md:py-0 flex flex-col justify-center max-w-[360px] w-full mx-auto animate-fadeIn" style={{ animationDelay: '50ms' }}>

          <div className="space-y-2 mb-6">
            <h1 className="text-xl font-medium tracking-tight text-white select-none">
              {loginTab === 'user' && userMode === 'register' ? 'Create your Torkq account' : 'Sign in to Torkq'}
            </h1>
            <p className="text-xs text-white/40 leading-relaxed select-none">
              {loginTab === 'admin'
                ? 'Accessing secure out-of-band security control plane console.'
                : userMode === 'register'
                  ? 'A virtual key is created automatically -- you can start chatting right after signing up.'
                  : 'Accessing the model inference and proxy gateway portal.'}
            </p>
          </div>

          {/* Secure Partitioned Dual-Tab Login */}
          <div className="grid grid-cols-2 gap-1 bg-[#0c121a] p-1 border border-white/[0.06] rounded-[2px] mb-6">
            <button
              type="button"
              onClick={() => {
                setLoginTab('user');
                resetFields();
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
                resetFields();
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

          {loginTab === 'user' && (
            <div className="flex items-center justify-center space-x-1 mb-5 text-[11px] font-mono select-none">
              <button
                type="button"
                onClick={() => { setUserMode('login'); setError(null); }}
                className={`px-2.5 py-1 rounded-[1px] transition-all cursor-pointer ${
                  userMode === 'login' ? 'text-white font-bold border-b border-indigo-400' : 'text-white/35 hover:text-white/60'
                }`}
              >
                Log In
              </button>
              <span className="text-white/15">/</span>
              <button
                type="button"
                onClick={() => { setUserMode('register'); setError(null); }}
                className={`px-2.5 py-1 rounded-[1px] transition-all cursor-pointer ${
                  userMode === 'register' ? 'text-white font-bold border-b border-indigo-400' : 'text-white/35 hover:text-white/60'
                }`}
              >
                Register
              </button>
            </div>
          )}

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
                {loginTab === 'admin' ? 'Administrator Email' : 'Email'}
              </label>
              <input
                id="email-field"
                type={loginTab === 'admin' ? 'text' : 'email'}
                autoComplete="email"
                required
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (error) setError(null);
                }}
                disabled={isSubmitting}
                placeholder={loginTab === 'admin' ? 'admin@mono.ai' : 'you@company.com'}
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
                  autoComplete={loginTab === 'user' && userMode === 'register' ? 'new-password' : 'current-password'}
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

            {loginTab === 'user' && userMode === 'register' && (
              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-white/60 select-none">
                  Confirm Passkey
                </label>
                <input
                  id="confirm-password-field"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value);
                    if (error) setError(null);
                  }}
                  disabled={isSubmitting}
                  placeholder="••••••••••••"
                  className="w-full px-3 py-2 bg-[#0c121a]/60 border border-white/[0.08] rounded-[2px] text-xs text-white/90 placeholder-white/20 focus:border-indigo-500/50 focus:outline-none focus:ring-1 focus:ring-indigo-500/50 transition-all font-mono"
                />
              </div>
            )}

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
              {loginTab === 'admin'
                ? (isSubmitting ? 'Authorizing admin token...' : 'Access Control Plane')
                : userMode === 'register'
                  ? (isSubmitting ? 'Creating account...' : 'Create Account & Connect')
                  : (isSubmitting ? 'Verifying gateway node...' : 'Connect to Gateway')}
            </button>
          </form>

          {/* Dynamic helper card */}
          {loginTab === 'admin' ? (
            <div className="mt-6 pt-5 border-t border-white/[0.03] text-[10px] font-mono text-white/30 space-y-2 select-none">
              <span className="text-indigo-400 font-semibold block uppercase tracking-wider">
                Admin Clearances Available:
              </span>
              <div className="space-y-1 bg-rose-500/5 border border-rose-500/10 p-2 rounded-[1px]">
                <div>Operator: <strong className="text-rose-300 font-bold select-all">admin@mono.ai</strong></div>
                <div>Passkey: <strong className="text-white/70">admin</strong></div>
                <div className="pt-1.5 mt-1 border-t border-white/5">Operator: <strong className="text-rose-300 font-bold select-all">engineer@mono.ai</strong></div>
                <div>Passkey: <strong className="text-white/70">governance2026</strong></div>
              </div>
            </div>
          ) : (
            <div className="mt-6 pt-5 border-t border-white/[0.03] text-[10px] text-white/30 select-none">
              {userMode === 'login' ? (
                <span>
                  Don't have an account?{' '}
                  <button
                    type="button"
                    onClick={() => { setUserMode('register'); setError(null); }}
                    className="text-indigo-400 hover:text-indigo-300 hover:underline transition-all font-medium cursor-pointer"
                  >
                    Register
                  </button>{' '}
                  -- a virtual key is issued automatically.
                </span>
              ) : (
                <span>
                  Already have an account?{' '}
                  <button
                    type="button"
                    onClick={() => { setUserMode('login'); setError(null); }}
                    className="text-indigo-400 hover:text-indigo-300 hover:underline transition-all font-medium cursor-pointer"
                  >
                    Log in
                  </button>
                </span>
              )}
            </div>
          )}

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
