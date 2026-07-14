import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import InputCapsule from './components/InputCapsule';
import { ChatSession, Message, Attachment, ModelType, Artifact, Project, FileScanSummary } from './types';
import ArtifactPanel from './components/ArtifactPanel';
import SignIn from './components/SignIn';
import ModelsDirectory from './components/ModelsDirectory';
import ProjectsPanel from './components/ProjectsPanel';
import AdminDashboard from './components/admin/AdminDashboard';
import { useGateway } from './context/GatewayContext';

const PROJECT_COLORS = ['#c2703f', '#4f7cc2', '#5fae7a', '#a664c2', '#c25f8f', '#c2a83f'];

type AppTab = 'chats' | 'models' | 'projects' | 'admin';

// The active tab is driven by the URL path so a reload keeps you where you
// were and the browser back/forward buttons work. (SPA fallback serves
// index.html on every path -- see web/server.ts.)
function tabFromPath(): AppTab {
  const p = typeof window !== 'undefined' ? window.location.pathname : '/';
  if (p.startsWith('/admin')) return 'admin';
  if (p.startsWith('/projects')) return 'projects';
  if (p.startsWith('/models')) return 'models';
  return 'chats';
}
function pathForTab(tab: AppTab): string {
  return tab === 'chats' ? '/' : `/${tab}`;
}

export default function App() {
  const { chatHeaders, setAdminEmail, setAdminKey, loadAdminKeyForEmail } = useGateway();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    return sessionStorage.getItem('mono_authenticated') === 'true';
  });
  const [userEmail, setUserEmail] = useState<string>(() => {
    return sessionStorage.getItem('mono_user_email') || '';
  });
  const [userRole, setUserRole] = useState<'admin' | 'user'>(() => {
    return (sessionStorage.getItem('mono_user_role') as 'admin' | 'user') || 'user';
  });
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState<ModelType>('auto');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [suggestionText, setSuggestionText] = useState('');
  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null);
  const [isArtifactOpen, setIsArtifactOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<AppTab>(() => {
    // Prefer a persisted tab (survives reload even if the URL was lost), then
    // the URL path, then default to chats.
    const saved = sessionStorage.getItem('mono_active_tab') as AppTab | null;
    if (saved && ['chats', 'models', 'projects', 'admin'].includes(saved)) return saved;
    return tabFromPath();
  });
  const [projects, setProjects] = useState<Project[]>(() => {
    try {
      const saved = localStorage.getItem('mono_projects');
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  // Keep the URL in sync with the active tab (so reload restores it), and
  // update the tab when the user hits browser back/forward.
  useEffect(() => {
    sessionStorage.setItem('mono_active_tab', activeTab);
    const path = pathForTab(activeTab);
    if (window.location.pathname !== path) {
      window.history.pushState({ tab: activeTab }, '', path);
    }
  }, [activeTab]);

  useEffect(() => {
    const onPop = () => setActiveTab(tabFromPath());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const saveProjects = (updated: Project[]) => {
    setProjects(updated);
    localStorage.setItem('mono_projects', JSON.stringify(updated));
  };

  const handleCreateProject = (name: string, description: string): string => {
    const id = `project-${Date.now()}`;
    const now = Date.now();
    const project: Project = {
      id, name, description, instructions: '',
      color: PROJECT_COLORS[projects.length % PROJECT_COLORS.length],
      createdAt: now, updatedAt: now,
    };
    saveProjects([project, ...projects]);
    return id;
  };

  const handleUpdateProject = (id: string, patch: Partial<Project>) => {
    saveProjects(projects.map(p => p.id === id ? { ...p, ...patch, updatedAt: Date.now() } : p));
  };

  const handleDeleteProject = (id: string) => {
    saveProjects(projects.filter(p => p.id !== id));
    // Detach (don't delete) chats that belonged to it.
    saveSessions(sessions.map(s => s.projectId === id ? { ...s, projectId: undefined } : s));
    setSelectedProjectId(null);
  };

  const handleNewChatInProject = (projectId: string) => {
    const newSession: ChatSession = {
      id: `session-${Date.now()}`,
      title: 'New chat',
      model: selectedModel,
      timestamp: 'Just now',
      messages: [],
      projectId,
    };
    saveSessions([newSession, ...sessions]);
    setActiveSessionId(newSession.id);
    handleUpdateProject(projectId, {});
    setActiveTab('chats');
  };

  const handleOpenArtifact = (title: string, language: string, code: string, type: 'code' | 'preview' | 'document') => {
    setActiveArtifact({
      id: Date.now().toString(),
      title,
      language,
      code,
      type
    });
    setIsArtifactOpen(true);
  };

  // Initialize sessions from localStorage, or start with a single real empty
  // session (no pre-populated fake chat history).
  useEffect(() => {
    const saved = localStorage.getItem('mono_chat_sessions');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setSessions(parsed);
          setActiveSessionId(parsed[0].id);
          setSelectedModel(parsed[0].model as ModelType);
          return;
        }
      } catch (e) {
        console.error('Error loading saved sessions from localStorage:', e);
      }
    }
    const freshSession: ChatSession = {
      id: `session-${Date.now()}`,
      title: 'New chat',
      model: 'auto',
      timestamp: 'Just now',
      messages: []
    };
    setSessions([freshSession]);
    setActiveSessionId(freshSession.id);
  }, []);

  // Write changes to localStorage whenever sessions update
  const saveSessions = (updatedSessions: ChatSession[]) => {
    setSessions(updatedSessions);
    localStorage.setItem('mono_chat_sessions', JSON.stringify(updatedSessions));
  };

  const activeSession = sessions.find(s => s.id === activeSessionId) || null;

  const handleSelectSession = (id: string) => {
    setActiveSessionId(id);
    const sess = sessions.find(s => s.id === id);
    if (sess) {
      setSelectedModel(sess.model as ModelType);
    }
    setActiveTab('chats');
  };

  const handleNewChat = () => {
    const newSession: ChatSession = {
      id: `session-${Date.now()}`,
      title: 'New chat',
      model: selectedModel,
      timestamp: 'Just now',
      messages: []
    };
    const updated = [newSession, ...sessions];
    saveSessions(updated);
    setActiveSessionId(newSession.id);
    setActiveTab('chats');
  };

  const handleDeleteSession = (id: string) => {
    const updated = sessions.filter(s => s.id !== id);
    saveSessions(updated);
    if (activeSessionId === id && updated.length > 0) {
      setActiveSessionId(updated[0].id);
    } else if (updated.length === 0) {
      // Re-create a clean one if empty
      const emptySess: ChatSession = {
        id: `session-${Date.now()}`,
        title: 'New chat',
        model: selectedModel,
        timestamp: 'Just now',
        messages: []
      };
      saveSessions([emptySess]);
      setActiveSessionId(emptySess.id);
    }
  };

  const handleUpdateTitle = (newTitle: string) => {
    const updated = sessions.map(s => {
      if (s.id === activeSessionId) {
        return { ...s, title: newTitle };
      }
      return s;
    });
    saveSessions(updated);
  };

  const handleClearSession = () => {
    const updated = sessions.map(s => {
      if (s.id === activeSessionId) {
        return { ...s, messages: [] };
      }
      return s;
    });
    saveSessions(updated);
  };

  const handleSendMessage = async (content: string, attachments: Attachment[]) => {
    if (!activeSessionId) return;

    const timeString = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMessage: Message = {
      id: `msg-user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: timeString,
      attachments
    };

    // Append user message immediately
    const currentSession = sessions.find(s => s.id === activeSessionId);
    if (!currentSession) return;

    const updatedMessages = [...currentSession.messages, userMessage];
    
    // Auto rename "New chat" if it was the first message
    let currentTitle = currentSession.title;
    if (currentTitle === 'New chat' && content.trim()) {
      currentTitle = content.trim().split('\n')[0].substring(0, 32);
      if (currentTitle.length === 32) currentTitle += '...';
    }

    const updatedSession = {
      ...currentSession,
      title: currentTitle,
      messages: updatedMessages
    };

    const updatedSessionsList = sessions.map(s => s.id === activeSessionId ? updatedSession : s);
    saveSessions(updatedSessionsList);
    setIsLoading(true);

    try {
      // 1) Scan any attached files for PII server-side (extract + OCR +
      // detect). Only the REDACTED text is folded into the prompt, so the
      // model never sees raw file PII. A per-file summary is attached to the
      // user message for display.
      const fileScans: FileScanSummary[] = [];
      let redactedFileText = '';
      for (const att of attachments || []) {
        if (!att.base64) continue;
        try {
          const res = await fetch('/api/files/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...chatHeaders() },
            body: JSON.stringify({ filename: att.name, content_type: att.type, data_base64: att.base64 }),
          });
          const d = await res.json().catch(() => ({}));
          if (!res.ok) {
            fileScans.push({ name: att.name, blocked: false, labels: {}, blockedLabels: [], error: d?.error?.message || `HTTP ${res.status}` });
            continue;
          }
          // Split findings by action: BLOCK-classified labels (credit card,
          // gov id, secrets) block the whole request just like in chat;
          // REVERSIBLE labels are redacted and forwarded. PRESERVE findings
          // are detected but left in place, so they don't count as either.
          const redactedLabels: Record<string, number> = {};
          const blockedLabels = new Set<string>();
          for (const f of (d.findings || []) as Array<{ label: string; action: string }>) {
            if (f.action === 'BLOCK') blockedLabels.add(f.label);
            else if (f.action === 'REVERSIBLE') redactedLabels[f.label] = (redactedLabels[f.label] || 0) + 1;
          }
          fileScans.push({ name: att.name, blocked: !!d.blocked, labels: redactedLabels, blockedLabels: [...blockedLabels] });
          if (typeof d.redacted_text === 'string' && d.redacted_text.trim()) {
            redactedFileText += `\n\n[Attached file: ${att.name} — PII redacted before sending]\n${d.redacted_text.trim()}`;
          }
        } catch (err: any) {
          fileScans.push({ name: att.name, blocked: false, labels: {}, blockedLabels: [], error: err.message || 'scan failed' });
        }
      }
      if (fileScans.length > 0) {
        const withScans = { ...userMessage, fileScans };
        const msgs = updatedMessages.map(m => m.id === userMessage.id ? withScans : m);
        saveSessions(sessions.map(s => s.id === activeSessionId ? { ...updatedSession, messages: msgs } : s));
      }

      // A file containing BLOCK-classified PII (credit card, gov ID, secret)
      // blocks the whole request -- consistent with chat: BLOCK content never
      // reaches a model. Stop here and surface a blocked banner instead of
      // forwarding the (redacted) file text.
      const blockedFiles = fileScans.filter(fs => fs.blocked && fs.blockedLabels.length > 0);
      if (blockedFiles.length > 0) {
        const allLabels = Array.from(new Set(blockedFiles.flatMap(fs => fs.blockedLabels)));
        const blockedMessage: Message = {
          id: `msg-ai-blocked-${Date.now()}`,
          role: 'assistant',
          content: `This request was intercepted and blocked by the Torkq Policy Gateway. An attached file contains content classified BLOCK (${allLabels.join(', ')}), which is never sent to a model.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          guardrail: {
            type: allLabels.includes('SECRET') ? 'secret' : 'pii',
            status: 'blocked',
            title: 'Policy Violation: File Content Blocked',
            message: `Blocked file${blockedFiles.length > 1 ? 's' : ''}: ${blockedFiles.map(f => f.name).join(', ')}. Labels: ${allLabels.join(', ')}.`,
            details: allLabels,
          },
        };
        saveSessions(sessions.map(s => s.id === activeSessionId
          ? { ...updatedSession, messages: [...updatedMessages.map(m => m.id === userMessage.id ? { ...userMessage, fileScans } : m), blockedMessage] }
          : s));
        setIsLoading(false);
        return;
      }

      // 2) Format history for the model. Raw attachment bytes are NOT sent --
      // they've been replaced by the redacted text folded in below. A user
      // message the gateway already BLOCKED once is not resent verbatim
      // (its raw content never reached a model; resending would re-trigger
      // the same BLOCK on every later turn since the gateway re-scans the
      // whole history each call).
      const apiMessages = updatedMessages.map((m, idx) => {
        const wasBlocked = m.role === 'user' && updatedMessages[idx + 1]?.guardrail?.status === 'blocked';
        return {
          role: m.role,
          content: wasBlocked ? '[Message removed -- blocked by gateway policy on a previous attempt]' : m.content,
        };
      });

      // Fold the redacted file text into the newest user turn's content.
      if (redactedFileText && apiMessages.length > 0) {
        const last = apiMessages.length - 1;
        apiMessages[last] = { ...apiMessages[last], content: (apiMessages[last].content || '') + redactedFileText };
      }

      // If this chat belongs to a project with custom instructions, prepend
      // them as a system message so every chat in the project shares context.
      const chatProject = currentSession.projectId ? projects.find(p => p.id === currentSession.projectId) : null;
      const outboundMessages = chatProject?.instructions?.trim()
        ? [{ role: 'system', content: chatProject.instructions.trim() }, ...apiMessages]
        : apiMessages;

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...chatHeaders() },
        body: JSON.stringify({
          messages: outboundMessages,
          model: selectedModel,
          session_id: activeSessionId,
          systemInstruction: "You are a professional, highly scannable, and extremely helpful AI expert. Your prose text should be clean and structured. Use appropriate headings, inline elements, lists, or code blocks when answering coding or architecture requests. Format everything cleanly in Markdown."
        })
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error || 'Server returned an error response.');
      }

      // Append assistant message response
      const assistantMessage: Message = {
        id: `msg-ai-${Date.now()}`,
        role: 'assistant',
        content: data.content,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        guardrail: data.guardrail
      };

      const finalSession = {
        ...updatedSession,
        messages: [...updatedMessages, assistantMessage]
      };

      saveSessions(sessions.map(s => s.id === activeSessionId ? finalSession : s));

      // Auto-extract code blocks or long documents to Artifact Workspace panel
      const codeBlockMatch = /```(\w+)\n([\s\S]*?)\n```/.exec(data.content);
      if (codeBlockMatch) {
        const lang = codeBlockMatch[1];
        const code = codeBlockMatch[2];
        const isInteractive = ['html', 'svg'].includes(lang.toLowerCase());
        handleOpenArtifact(
          isInteractive ? 'Interactive UI Component' : `Generated Code Block`,
          lang,
          code,
          isInteractive ? 'preview' : 'code'
        );
      } else if (data.content.length > 800) {
        handleOpenArtifact(
          'Synthesized Technical Analysis',
          'markdown',
          data.content,
          'document'
        );
      }

    } catch (err: any) {
      console.error('Chat error:', err);
      
      // Gracefully inject an actionable system assistant block with key instructions
      const errorMessageText = `⚠️ **Error Communicating with the Torkq Gateway**\n\n${err.message || 'An unexpected error occurred.'}\n\n*   **Connection Check**: Go to Admin > Settings and confirm the Gateway URL, Admin Key, and Test Connection all succeed.\n*   **Virtual Key**: Confirm a Chat Virtual Key is set (Admin > Settings) and that the selected model is on its allowlist.`;

      const assistantMessage: Message = {
        id: `msg-ai-err-${Date.now()}`,
        role: 'assistant',
        content: errorMessageText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      const finalSession = {
        ...updatedSession,
        messages: [...updatedMessages, assistantMessage]
      };

      saveSessions(sessions.map(s => s.id === activeSessionId ? finalSession : s));
    } finally {
      setIsLoading(false);
    }
  };

  const handleModelChange = (model: ModelType) => {
    setSelectedModel(model);
    const updated = sessions.map(s => {
      if (s.id === activeSessionId) {
        return { ...s, model };
      }
      return s;
    });
    saveSessions(updated);
  };

  const handlePaidFlowPrompt = () => {
    // Calling AI studio UI tool logic for paid model flow
    console.log('User requested paid model setup - opening flow');
  };

  const handleSignIn = (email: string, role: 'admin' | 'user') => {
    setUserEmail(email);
    setUserRole(role);
    setIsAuthenticated(true);
    sessionStorage.setItem('mono_authenticated', 'true');
    sessionStorage.setItem('mono_user_email', email);
    sessionStorage.setItem('mono_user_role', role);
    if (role === 'admin') {
      setActiveTab('admin');
      // Recall this admin's gateway key from the gateway's own DB (see
      // gateway/auth/admin_account_store.py) so they don't have to re-paste
      // it into Settings every session -- only the first time ever.
      setAdminEmail(email);
      loadAdminKeyForEmail(email).then((key) => {
        if (key) setAdminKey(key);
      });
    } else {
      setActiveTab('chats');
    }
  };

  const handleSignOut = () => {
    setIsAuthenticated(false);
    setUserRole('user');
    sessionStorage.removeItem('mono_authenticated');
    sessionStorage.removeItem('mono_user_email');
    sessionStorage.removeItem('mono_user_role');
    sessionStorage.removeItem('mono_active_tab');
  };

  if (!isAuthenticated) {
    return <SignIn onSignIn={handleSignIn} />;
  }

  // Double check protection: if a user is not an admin, they should never be allowed to view the admin tab
  if (activeTab === 'admin' && userRole !== 'admin') {
    setActiveTab('chats');
  }

  if (activeTab === 'admin') {
    return (
      <AdminDashboard
        onBackToWorkspace={() => setActiveTab('chats')}
        onSignOut={handleSignOut}
        userEmail={userEmail}
      />
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0A0E14] select-none font-sans">
      
      {/* Panel A: The High-Density Left Navigation Sidebar */}
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        isCollapsed={isSidebarCollapsed}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        setIsCollapsed={setIsSidebarCollapsed}
        onSignOut={handleSignOut}
        userEmail={userEmail}
        userRole={userRole}
        activeTab={activeTab}
        onChangeTab={(tab) => { if (tab === 'projects') setSelectedProjectId(null); setActiveTab(tab); }}
        projectCount={projects.length}
      />

      {/* Persistent Flex Row Wrapper */}
      <div className="flex-1 flex flex-row h-full min-w-0 relative">

        {activeTab === 'models' ? (
          <ModelsDirectory
            selectedModel={selectedModel}
            onChangeModel={handleModelChange}
            onRequestPaidFlow={handlePaidFlowPrompt}
          />
        ) : activeTab === 'projects' ? (
          <ProjectsPanel
            projects={projects}
            sessions={sessions}
            selectedProjectId={selectedProjectId}
            onSelectProject={setSelectedProjectId}
            onCreateProject={handleCreateProject}
            onUpdateProject={handleUpdateProject}
            onDeleteProject={handleDeleteProject}
            onOpenChat={handleSelectSession}
            onNewChatInProject={handleNewChatInProject}
          />
        ) : (
          /* Main chat stream and input layout wrapper */
          <div className="flex-1 flex flex-col h-full min-w-0 relative">
            
            {/* Panel B: Workspace Canvas (Main Chat Stream) */}
            <ChatArea
              session={activeSession}
              onUpdateTitle={handleUpdateTitle}
              onClearSession={handleClearSession}
              isSidebarCollapsed={isSidebarCollapsed}
              onToggleSidebar={() => setIsSidebarCollapsed(false)}
              isLoading={isLoading}
              onSelectSuggestion={(text) => setSuggestionText(text)}
              onOpenInArtifact={handleOpenArtifact}
            />

            {/* Panel C: Integrated Multi-Utility Input Capsule */}
            <div className="absolute bottom-0 left-0 right-0 z-10 pointer-events-none">
              <div className="pointer-events-auto">
                <InputCapsule
                  onSendMessage={handleSendMessage}
                  selectedModel={selectedModel}
                  onChangeModel={handleModelChange}
                  isLoading={isLoading}
                  onRequestPaidFlow={handlePaidFlowPrompt}
                  suggestionText={suggestionText}
                  onSuggestionTextConsumed={() => setSuggestionText('')}
                />
              </div>
            </div>

          </div>
        )}

      </div>

      {/* Panel D: Dynamic Right-Hand Artifacts Panel */}
      <ArtifactPanel
        artifact={activeArtifact}
        isOpen={isArtifactOpen}
        onClose={() => setIsArtifactOpen(false)}
      />
    </div>
  );
}
