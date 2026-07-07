import React, { useState, useRef, useEffect } from 'react';
import { 
  ChevronDown, 
  Share2, 
  FileText, 
  FileArchive, 
  Image as ImageIcon, 
  FileCode, 
  Download, 
  User, 
  Sparkles, 
  Check, 
  Copy, 
  Settings,
  X,
  HelpCircle,
  FileUp,
  RefreshCw,
  Clock,
  Terminal,
  Cpu,
  BookOpen,
  Layers,
  ShieldAlert,
  Lock,
  Key,
  Shield
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import CodeBlock from './CodeBlock';
import GuardrailAlert from './GuardrailAlert';
import { ChatSession, Message, Attachment } from '../types';

interface ChatAreaProps {
  session: ChatSession | null;
  onUpdateTitle: (newTitle: string) => void;
  onClearSession: () => void;
  isSidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  isLoading: boolean;
  onSelectSuggestion?: (text: string) => void;
  onOpenInArtifact?: (title: string, language: string, code: string, type: 'code' | 'preview' | 'document') => void;
}

const STARTER_SUGGESTIONS = [
  {
    category: 'PII Scanner',
    prompt: 'Send a request containing a fake SSN and credit card number',
    icon: ShieldAlert,
    color: 'text-amber-400/80',
  },
  {
    category: 'RBAC Authorization',
    prompt: 'Try to access an admin-only model with a viewer role',
    icon: Lock,
    color: 'text-rose-400/80',
  },
  {
    category: 'Secret Detection',
    prompt: 'Paste this AWS key and ask me to debug it',
    icon: Key,
    color: 'text-indigo-400/80',
  },
  {
    category: 'Code Vulnerability',
    prompt: 'Ask me to write SQL with a vulnerability',
    icon: Shield,
    color: 'text-emerald-400/80',
  },
];

export default function ChatArea({
  session,
  onUpdateTitle,
  onClearSession,
  isSidebarCollapsed,
  onToggleSidebar,
  isLoading,
  onSelectSuggestion,
  onOpenInArtifact
}: ChatAreaProps) {
  const [showSessionMenu, setShowSessionMenu] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  const [copiedShareLink, setCopiedShareLink] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleInput, setTitleInput] = useState('');
  
  const bottomRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session?.messages, isLoading]);

  // Close menus on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowSessionMenu(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleStartRename = () => {
    if (!session) return;
    setTitleInput(session.title);
    setEditingTitle(true);
    setShowSessionMenu(false);
  };

  const handleSaveRename = (e: React.FormEvent) => {
    e.preventDefault();
    if (titleInput.trim() && session) {
      onUpdateTitle(titleInput.trim());
    }
    setEditingTitle(false);
  };

  const handleShare = () => {
    setShowShareModal(true);
    setCopiedShareLink(false);
  };

  const copyShareLink = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopiedShareLink(true);
    setTimeout(() => setCopiedShareLink(false), 2000);
  };

  const handleCopyMessage = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMessageId(id);
    setTimeout(() => setCopiedMessageId(null), 2000);
  };

  const getFileIcon = (mimeType: string) => {
    if (mimeType.startsWith('image/')) return ImageIcon;
    if (mimeType.includes('zip') || mimeType.includes('tar') || mimeType.includes('gzip')) return FileArchive;
    if (mimeType.includes('javascript') || mimeType.includes('typescript') || mimeType.includes('json') || mimeType.includes('html') || mimeType.includes('css')) return FileCode;
    return FileText;
  };

  const getReadableSize = (sizeStr: string) => {
    return sizeStr;
  };

  const handleDownloadMock = (att: Attachment) => {
    // Standard mock download feedback
    const element = document.createElement("a");
    const file = new Blob([att.text || "Mock content payload of downloaded asset"], { type: att.type });
    element.href = URL.createObjectURL(file);
    element.download = att.name;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#0A0E14] text-[#e0e0e0] relative overflow-hidden">
      
      {/* Panel B: Fixed Header Bar */}
      <header className="h-16 border-b border-white/[0.08] bg-[#0A0E14]/90 backdrop-blur-md flex items-center justify-between px-6 shrink-0 z-10">
        <div className="flex items-center space-x-4 min-w-0">
          {isSidebarCollapsed && (
            <button 
              onClick={onToggleSidebar}
              className="text-white/40 hover:text-white/85 p-2 rounded-[2px] hover:bg-white/5 mr-1 cursor-pointer transition-all flex items-center justify-center border border-white/[0.05]"
              title="Expand sidebar"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" /><path d="M9 3v18" /></svg>
            </button>
          )}

          {editingTitle ? (
            <form onSubmit={handleSaveRename} className="flex items-center space-x-2">
              <input
                type="text"
                value={titleInput}
                onChange={(e) => setTitleInput(e.target.value)}
                onBlur={() => setEditingTitle(false)}
                className="bg-white/5 border border-white/10 text-[13px] rounded-[2px] px-3 py-1 text-white/95 focus:outline-none focus:border-rose-500/30 font-semibold font-mono"
                autoFocus
              />
            </form>
          ) : (
            <div className="relative" ref={menuRef}>
              <button 
                onClick={() => setShowSessionMenu(!showSessionMenu)}
                className="flex items-center space-x-2 text-[14px] font-bold text-white/90 hover:text-white transition-colors cursor-pointer px-2.5 py-1.5 rounded-[2px] hover:bg-white/[0.03]"
              >
                <span className="truncate max-w-[200px] md:max-w-md font-mono tracking-wider uppercase">
                  {session ? session.title : "New Transaction"}
                </span>
                <ChevronDown size={14} className="text-white/40 mt-0.5 shrink-0" />
              </button>

              {/* Session Dropdown Menu */}
              {showSessionMenu && session && (
                <div className="absolute left-0 mt-2 w-60 bg-[#0c121a] border border-white/[0.08] rounded-[2px] shadow-2xl py-1.5 z-20">
                  <div className="px-4 py-2 border-b border-white/5 mb-1">
                    <p className="text-[9px] font-mono uppercase tracking-widest text-white/40">Session Config</p>
                    <p className="text-xs text-white/60 truncate font-mono mt-0.5">Model: {session.model}</p>
                  </div>
                  <button
                    onClick={handleStartRename}
                    className="flex items-center space-x-2.5 w-full text-left px-4 py-2 text-xs text-white/70 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
                  >
                    <FileText size={11} className="text-rose-300" />
                    <span>Rename Transaction</span>
                  </button>
                  <button
                    onClick={() => {
                      onClearSession();
                      setShowSessionMenu(false);
                    }}
                    className="flex items-center space-x-2.5 w-full text-left px-4 py-2 text-xs text-red-400 hover:text-red-300 hover:bg-white/5 transition-colors cursor-pointer"
                  >
                    <X size={11} />
                    <span>Clear Transaction Logs</span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right side utilities */}
        <div className="flex items-center space-x-3.5 animate-fadeIn">
          <div className="hidden sm:flex items-center space-x-2.5 px-3.5 py-1.5 bg-rose-500/10 rounded-[2px] border border-rose-500/25 shadow-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400 inline-block animate-pulse shadow-[0_0_8px_rgba(244,63,94,0.5)]"></span>
            <span className="text-[9px] font-mono text-rose-300 uppercase tracking-widest font-bold flex items-center gap-1.5">
              <span>Proxy Shield</span>
              <span className="text-rose-500 font-normal">|</span>
              <span className="text-white/85 font-semibold">RBAC ✓</span>
              <span className="text-white/30">•</span>
              <span className="text-white/85 font-semibold">PII ✓</span>
              <span className="text-white/30">•</span>
              <span className="text-white/85 font-semibold">Secrets ✓</span>
              <span className="text-white/30">•</span>
              <span className="text-white/85 font-semibold">Exploits ✓</span>
            </span>
          </div>

          <button 
            onClick={handleShare}
            className="flex items-center space-x-2 px-3 py-1.5 text-xs text-white/80 hover:text-white hover:bg-white/[0.04] border border-white/[0.08] hover:border-white/[0.15] rounded-[2px] transition-all font-semibold tracking-wide shadow-sm cursor-pointer"
          >
            <Share2 size={12} className="text-rose-300" />
            <span>Share</span>
          </button>
        </div>
      </header>

      {/* Primary Conversational Feed Area */}
      <div className="flex-1 overflow-y-auto px-6 py-8 scrollbar-thin scrollbar-thumb-white/5">
        <div className="max-w-3xl mx-auto space-y-12">
          
          {!session || session.messages.length === 0 ? (
            /* Editorial Landing Screen */
            <div className="flex flex-col items-center justify-center py-20 text-center space-y-6">
              <div className="w-12 h-12 bg-[#0c121a]/90 border border-rose-500/30 rounded-[2px] flex items-center justify-center shadow-[0_0_15px_rgba(244,63,94,0.04)] animate-pulse">
                <Shield size={20} className="text-rose-400" />
              </div>
              <div className="space-y-2.5">
                <h2 className="text-xl font-mono tracking-widest text-white/95 font-semibold uppercase">
                  MonoAI Policy Gateway
                </h2>
                <p className="text-xs text-white/45 max-w-lg mx-auto leading-relaxed font-light font-sans">
                  Every request passes through your gateway's policies before it reaches a model. Test real-time RBAC compliance, PII redaction, secret scanning, and vulnerability detection below.
                </p>
              </div>

              {/* Minimal suggestions bento style */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-xl pt-6">
                {STARTER_SUGGESTIONS.map((s, idx) => {
                  const IconComponent = s.icon;
                  return (
                    <button
                      key={idx}
                      onClick={() => onSelectSuggestion?.(s.prompt)}
                      className="p-3.5 bg-[#0e141c]/40 border border-white/[0.05] hover:border-white/[0.15] hover:bg-white/[0.01] rounded-[2px] text-left transition-all duration-200 group flex items-start space-x-3 focus:outline-none cursor-pointer"
                    >
                      <div className="p-1.5 bg-white/[0.03] border border-white/[0.06] rounded-[1px] shrink-0 group-hover:bg-white/[0.06] group-hover:border-white/[0.1] transition-all">
                        <IconComponent size={13} className={`${s.color} transition-all duration-300 group-hover:scale-105`} />
                      </div>
                      <div className="flex flex-col min-w-0 font-mono">
                        <span className="text-[9px] font-bold uppercase tracking-widest text-white/30 group-hover:text-white/50 transition-colors">
                          {s.category}
                        </span>
                        <p className="text-[11px] text-white/75 mt-1 font-medium leading-relaxed group-hover:text-white/95 transition-colors font-sans">
                          {s.prompt}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            /* Conversational Feed Streams */
            <div className="space-y-10">
              {session.messages.map((msg) => {
                const isUser = msg.role === 'user';
                return (
                  <div 
                    key={msg.id} 
                    className="flex w-full justify-start group/msg animate-fadeIn"
                    style={{ animationDuration: '200ms' }}
                  >
                    <div className="flex flex-col space-y-2.5 w-full items-start">
                      {/* Message Header Profile Block */}
                      <div className="flex items-center space-x-2.5 w-full">
                        <div className={`w-5 h-5 rounded-[2px] flex items-center justify-center text-[10px] font-mono border shrink-0 ${
                          isUser 
                            ? 'bg-white/5 border-white/10 text-white/70' 
                            : 'bg-rose-500/10 border-rose-500/20 text-rose-400 font-bold'
                        }`}>
                          {isUser ? <User size={10} /> : 'M'}
                        </div>
                        <span className="text-[11px] font-bold text-white/80 tracking-wider font-mono uppercase">
                          {isUser ? 'User Core' : 'Gateway Proxy'}
                        </span>
                        <span className="text-[9px] font-mono text-white/30 font-light flex items-center space-x-1">
                          <Clock size={8} className="mr-0.5 mt-0.5" />
                          <span>{msg.timestamp}</span>
                        </span>

                        {/* Spacer to push actions or keep tidy */}
                        <div className="flex-grow min-w-4" />

                        {/* Micro actions on hover */}
                        <div className="opacity-0 group-hover/msg:opacity-100 transition-opacity flex items-center space-x-2">
                          <button
                            onClick={() => handleCopyMessage(msg.id, msg.content)}
                            className="p-1 text-white/45 hover:text-white hover:bg-white/5 rounded transition-colors"
                            title="Copy message content"
                          >
                            {copiedMessageId === msg.id ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                          </button>
                        </div>
                      </div>

                      {/* Attached inline assets (Panel B specification) */}
                      {msg.attachments && msg.attachments.length > 0 && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 pb-2 w-full max-w-lg">
                          {msg.attachments.map((att) => {
                            const FileIcon = getFileIcon(att.type);
                            return (
                              <div 
                                key={att.id}
                                className="flex items-center justify-between p-3 bg-[#0c121a]/60 border border-white/[0.08] rounded-[2px] hover:border-white/15 transition-all group/card w-full"
                              >
                                <div className="flex items-center space-x-3 min-w-0 font-mono">
                                  <div className="w-9 h-9 bg-white/5 border border-white/10 rounded-[1px] flex items-center justify-center shrink-0">
                                    <FileIcon size={16} className="text-white/60" />
                                  </div>
                                  <div className="flex flex-col min-w-0">
                                    <span className="text-xs font-medium text-white/90 truncate pr-2">
                                      {att.name}
                                    </span>
                                    <span className="text-[10px] font-mono text-white/45">
                                      {getReadableSize(att.size)}
                                    </span>
                                  </div>
                                </div>
                                
                                <button
                                  onClick={() => handleDownloadMock(att)}
                                  className="text-[11px] font-bold text-white/50 hover:text-white transition-all pr-2"
                                  title="View attachment file"
                                >
                                  View
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Guardrail Decision Card */}
                      {!isUser && msg.guardrail && (
                        <div className="w-full max-w-2xl mt-1.5">
                          <GuardrailAlert decision={msg.guardrail} />
                        </div>
                      )}

                      {/* Edge-to-edge Document Prose Content */}
                      <div className="text-[15px] leading-[1.6] font-sans text-white/90 font-normal tracking-normal max-w-none pl-0.5 text-left">
                        {isUser ? (
                          <p className="whitespace-pre-wrap">{msg.content}</p>
                        ) : (
                          <div className="prose prose-invert max-w-none prose-sm prose-p:leading-[1.6] text-left">
                            <ReactMarkdown
                              components={{
                                pre({ children }) {
                                  return <>{children}</>;
                                },
                                code({ className, children, ...props }) {
                                  const match = /language-(\w+)/.exec(className || '');
                                  return match ? (
                                    <CodeBlock
                                      language={match[1]}
                                      value={String(children).replace(/\n$/, '')}
                                      onOpenInArtifact={onOpenInArtifact}
                                    />
                                  ) : (
                                    <code className="px-1.5 py-0.5 bg-white/5 border border-white/10 rounded font-mono text-[13px] text-rose-300/90 font-light" {...props}>
                                      {children}
                                    </code>
                                  );
                                }
                              }}
                            >
                              {msg.content}
                            </ReactMarkdown>
                          </div>
                        )}
                      </div>

                    </div>
                  </div>
                );
              })}

              {/* Streaming loading state */}
              {isLoading && (
                <div className="flex flex-col space-y-3">
                  <div className="flex items-center space-x-2.5">
                    <div className="w-6 h-6 rounded-md bg-white text-[#191919] border border-white flex items-center justify-center text-xs font-bold font-mono">
                      M
                    </div>
                    <span className="text-[12px] font-semibold text-white/80 tracking-wide">
                      MonoAI
                    </span>
                    <span className="text-[10px] text-white/30 flex items-center space-x-1 font-mono">
                      <RefreshCw size={10} className="animate-spin mr-1 text-white/40" />
                      <span>Thinking...</span>
                    </span>
                  </div>
                  <div className="flex items-center space-x-1.5 pl-0.5">
                    <div className="w-2 h-2 bg-white/40 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                    <div className="w-2 h-2 bg-white/40 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                    <div className="w-2 h-2 bg-white/40 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                  </div>
                </div>
              )}
            </div>
          )}

          <div ref={bottomRef} className="h-48 shrink-0" />
        </div>
      </div>

      {/* Share Modal Backdrop & Popup */}
      {showShareModal && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#0c121a] border border-white/[0.08] rounded-[2px] max-w-md w-full p-6 space-y-4 shadow-2xl relative font-mono">
            <button 
              onClick={() => setShowShareModal(false)}
              className="absolute top-4 right-4 text-white/40 hover:text-white"
            >
              <X size={16} />
            </button>
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">Share transaction</h3>
              <p className="text-[11px] text-white/50 leading-relaxed font-sans">
                Generate a custom shareable link to publish this gateway transaction log with other team members or security auditors.
              </p>
            </div>
            <div className="flex items-center space-x-2 bg-[#060a0f] border border-white/10 rounded-[1px] p-2">
              <span className="text-[10px] text-white/40 truncate flex-1 font-mono select-all">
                {window.location.href}
              </span>
              <button
                onClick={copyShareLink}
                className="px-3 py-1.5 bg-white hover:bg-white/90 text-black text-xs font-bold rounded-[1px] transition-all shrink-0 flex items-center space-x-1"
              >
                {copiedShareLink ? (
                  <>
                    <Check size={12} className="text-emerald-700" />
                    <span>COPIED</span>
                  </>
                ) : (
                  <>
                    <Copy size={12} />
                    <span>COPY</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
