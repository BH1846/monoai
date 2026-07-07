import React, { useState } from 'react';
import { 
  Plus, 
  MessageSquare, 
  FolderKanban, 
  Sparkles, 
  Settings, 
  Terminal, 
  Code, 
  History, 
  MoreHorizontal, 
  ChevronLeft, 
  ChevronRight, 
  LogOut,
  User,
  Trash2,
  Share2,
  Cpu,
  Shield
} from 'lucide-react';
import { ChatSession } from '../types';

interface SidebarProps {
  sessions: ChatSession[];
  activeSessionId: string;
  isCollapsed: boolean;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession: (id: string) => void;
  setIsCollapsed: (collapsed: boolean) => void;
  userEmail?: string;
  onSignOut?: () => void;
  userRole?: 'admin' | 'user';
  activeTab?: 'chats' | 'models' | 'admin';
  onChangeTab?: (tab: 'chats' | 'models' | 'admin') => void;
}

export default function Sidebar({
  sessions,
  activeSessionId,
  isCollapsed,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  setIsCollapsed,
  userEmail = "rahulbalaskandan1511@gmail.com",
  onSignOut,
  userRole = 'user',
  activeTab = 'chats',
  onChangeTab
}: SidebarProps) {
  const [hoveredSessionId, setHoveredSessionId] = useState<string | null>(null);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  // Derive simple human-friendly name from email
  const userName = userEmail.split('@')[0].replace(/[._]/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase());

  const mainNavItems = [
    { id: 'chats' as const, label: 'Chats', icon: MessageSquare, active: activeTab === 'chats' },
    { id: 'models' as const, label: 'Models Directory', icon: Cpu, active: activeTab === 'models' },
    { id: 'projects' as const, label: 'Projects', icon: FolderKanban, count: '3', active: false },
  ];

  return (
    <div 
      className={`relative flex flex-col h-screen bg-[#060A0F] border-r border-white/[0.08] transition-all duration-300 ${
        isCollapsed ? 'w-0 overflow-hidden opacity-0 pointer-events-none' : 'w-64'
      }`}
      style={{ minWidth: isCollapsed ? '0px' : '256px' }}
    >
      {/* Top Brand & New Chat */}
      <div className="h-16 px-5 border-b border-white/[0.08] flex items-center justify-between shrink-0 bg-[#090E15]/40">
        <div className="flex items-center space-x-2.5">
          <div className="w-5 h-5 bg-rose-500/10 border border-rose-500/30 rounded-[2px] flex items-center justify-center font-mono text-[10px] text-rose-400 font-bold">
            M
          </div>
          <span className="font-sans text-[13px] tracking-widest text-white/90 font-bold uppercase">
            MonoAI Gateway
          </span>
        </div>
        <button 
          onClick={() => setIsCollapsed(true)}
          className="text-white/40 hover:text-white/80 transition-colors p-1 rounded-[1px] hover:bg-white/5 cursor-pointer"
          title="Collapse sidebar"
        >
          <ChevronLeft size={15} />
        </button>
      </div>

      <div className="p-3 border-b border-white/[0.04] shrink-0">
        <button
          onClick={onNewChat}
          className="flex items-center justify-between w-full py-2 px-3 bg-[#0D141E]/50 hover:bg-white/[0.03] text-white/90 border border-white/[0.06] hover:border-white/[0.12] rounded-[2px] text-[11px] font-semibold tracking-wide transition-all duration-150 cursor-pointer shadow-sm"
        >
          <span className="flex items-center space-x-2">
            <Plus size={13} className="opacity-70 text-rose-300" />
            <span>New Session</span>
          </span>
          <span className="opacity-30 text-[9px] font-mono font-light px-1.5 py-0.5 bg-white/5 border border-white/10 rounded-[1px]">⌘K</span>
        </button>
      </div>

      {/* Main Utilities Scroll Container */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-7 scrollbar-thin scrollbar-thumb-white/5">
        {/* Navigation Block */}
        <div className="space-y-1">
          {mainNavItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => {
                  if (item.id === 'chats' || item.id === 'models') {
                    onChangeTab?.(item.id);
                  }
                }}
                className={`flex items-center justify-between w-full px-3 py-2 rounded-[2px] text-[12px] font-medium transition-all cursor-pointer ${
                  item.active 
                    ? 'text-white bg-white/[0.05] font-semibold border border-white/[0.04]' 
                    : 'text-white/60 hover:text-white hover:bg-white/[0.02] border border-transparent'
                }`}
              >
                <div className="flex items-center space-x-2.5">
                  <Icon size={14} className={`${item.active ? 'text-rose-300' : 'opacity-60'}`} />
                  <span className="tracking-wide">{item.label}</span>
                </div>
                {item.count && (
                  <span className="text-[9px] font-mono px-1.5 py-0.5 bg-white/10 text-white/70 rounded-[1px]">
                    {item.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Recents Timeline */}
        <div className="space-y-3">
          <div className="flex items-center justify-between px-3.5">
            <span className="text-[10px] font-mono uppercase tracking-widest text-white/30 font-bold">
              Recent Chats
            </span>
            <History size={11} className="text-white/30" />
          </div>

          <div className="space-y-1 max-h-60 overflow-y-auto pr-1">
            {sessions.length === 0 ? (
              <div className="px-3.5 py-2.5 text-xs text-white/30 italic">
                No past sessions
              </div>
            ) : (
              sessions.map((session) => (
                <div
                  key={session.id}
                  onMouseEnter={() => setHoveredSessionId(session.id)}
                  onMouseLeave={() => {
                    setHoveredSessionId(null);
                    setActiveMenuId(null);
                  }}
                  className={`group relative flex items-center justify-between w-full px-3 py-2 rounded-[2px] text-[12px] transition-all border ${
                    session.id === activeSessionId
                      ? 'text-white bg-white/[0.04] border-white/[0.06]'
                      : 'text-white/60 hover:text-white hover:bg-white/[0.01] border-transparent'
                  }`}
                >
                  <button
                    onClick={() => {
                      onChangeTab?.('chats');
                      onSelectSession(session.id);
                    }}
                    className="flex-1 text-left truncate pr-8 font-mono"
                    title={session.title}
                  >
                    {session.title || "Untitled Session"}
                  </button>
 
                  {/* Actions visible on hover */}
                  {(hoveredSessionId === session.id || activeMenuId === session.id) && (
                    <div className="absolute right-2 flex items-center bg-[#060A0F] group-hover:bg-white/[0.02] pl-1 rounded-[1px]">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(session.id);
                        }}
                        className="p-1 text-white/40 hover:text-red-400 transition-colors rounded-[1px]"
                        title="Delete session"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* User profile block & footer */}
      <div className="p-4 border-t border-white/[0.08] bg-[#060A0F]">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2.5 max-w-[80%]">
            <div className="w-8 h-8 rounded-[2px] bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
              <span className="text-[10px] font-semibold text-rose-300 font-mono">AD</span>
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-semibold text-white/80 truncate">
                {userName}
              </span>
              <span className="text-[9px] text-white/40 uppercase tracking-wider font-mono">
                SEC_AUDITOR
              </span>
            </div>
          </div>
          <button 
            onClick={() => onSignOut && onSignOut()} 
            className="text-white/40 hover:text-white/80 transition-colors p-1.5 rounded-[2px] hover:bg-white/5"
            title="Sign Out"
          >
            <LogOut size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
