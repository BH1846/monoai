import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import InputCapsule from './components/InputCapsule';
import { ChatSession, Message, Attachment, ModelType, Artifact } from './types';
import ArtifactPanel from './components/ArtifactPanel';
import SignIn from './components/SignIn';
import ModelsDirectory from './components/ModelsDirectory';
import AdminDashboard from './components/admin/AdminDashboard';
import { useGateway } from './context/GatewayContext';

// Pre-populated high-fidelity sessions to ensure professional density on first load
const INITIAL_MOCK_SESSIONS: ChatSession[] = [
  {
    id: 'session-1',
    title: 'Express + Vite Architecture',
    model: 'auto',
    timestamp: '2 hours ago',
    messages: [
      {
        id: 'msg-1',
        role: 'user',
        content: 'What is the optimal folder structure for a full-stack Express + React application utilizing Vite? Keep it production-ready and modular.',
        timestamp: '10:14 AM'
      },
      {
        id: 'msg-2',
        role: 'assistant',
        content: 'An elegant, production-ready directory structure for an Express + Vite React application isolates server logic from frontend concerns while remaining compact and easy to bundle.\n\nHere is the recommended architecture:\n\n```text\n├── dist/                    # Production bundle outputs (compiled assets & server)\n│   ├── index.html           # Production static client bundle entry\n│   └── server.cjs           # Self-contained bundled Express backend\n├── src/                     # Client-side React applications\n│   ├── components/          # Reusable shared layout components\n│   ├── App.tsx              # Main coordinate UI layout\n│   ├── main.tsx             # Vite frontend bootstrap entry\n│   └── index.css            # Unified Tailwind global styling imports\n├── server.ts                # TypeScript Express server (dev & API route proxy)\n├── package.json             # Single scripts manager & dependencies block\n└── vite.config.ts           # Development dev server and asset configuration\n```\n\n### Key Design Guidelines\n1. **Unified package.json**: Avoid nested directory configuration. Keep dependencies, build scripts, and dev scripts unified in the workspace root for cleaner container routing.\n2. **Vite Development Middleware**: During local runs, configure the Express app to leverage `createViteServer` in middleware mode to enjoy instant bundle compilation on port `3000`.',
        timestamp: '10:15 AM'
      }
    ]
  },
  {
    id: 'session-2',
    title: 'CSS Variable Theme Specs',
    model: 'auto',
    timestamp: '1 day ago',
    messages: [
      {
        id: 'msg-3',
        role: 'user',
        content: 'Provide a clean, modern color spectrum for a charcoal/matte monochrome editor interface.',
        timestamp: 'Yesterday'
      },
      {
        id: 'msg-4',
        role: 'assistant',
        content: 'To achieve a warm charcoal matte feel, avoid true pitch blacks (`#000000`) and instead choose deeply saturated, dark neutral hues. This reduces eye fatigue and produces a distinctive premium brand texture.\n\nHere are the hex coordinates:\n\n*   **Primary Background:** `#191919` (matte coal canvas)\n*   **Sidebar Background:** `#1b1b19` (slightly warmer charcoal)\n*   **Integrated Containers:** `#242422` (mid-gray matte anchor)\n*   **Low-Contrast Borders:** `rgba(255, 255, 255, 0.08)` (ultra-thin borders)\n*   **Active Accents:** `rgba(255, 255, 255, 0.9)` (soft off-whites instead of harsh blues)',
        timestamp: 'Yesterday'
      }
    ]
  }
];

export default function App() {
  const { chatHeaders, setAdminEmail, setAdminKey, loadAdminKeyForEmail } = useGateway();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    return sessionStorage.getItem('mono_authenticated') === 'true';
  });
  const [userEmail, setUserEmail] = useState<string>(() => {
    return sessionStorage.getItem('mono_user_email') || 'rahulbalaskandan1511@gmail.com';
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
  const [activeTab, setActiveTab] = useState<'chats' | 'models' | 'admin'>('chats');

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

  // Initialize sessions from localStorage or fallback to default pre-populated sessions
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
    setSessions(INITIAL_MOCK_SESSIONS);
    setActiveSessionId(INITIAL_MOCK_SESSIONS[0].id);
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
      // Format session messages to send to server proxy
      // We pass the full context for rich history dialogue!
      const apiMessages = updatedMessages.map(m => ({
        role: m.role,
        content: m.content,
        attachments: m.attachments?.map(att => ({
          name: att.name,
          type: att.type,
          base64: att.base64,
          text: att.text
        }))
      }));

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...chatHeaders() },
        body: JSON.stringify({
          messages: apiMessages,
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
      const errorMessageText = `⚠️ **Error Communicating with the MonoAI Gateway**\n\n${err.message || 'An unexpected error occurred.'}\n\n*   **Connection Check**: Go to Admin > Settings and confirm the Gateway URL, Admin Key, and Test Connection all succeed.\n*   **Virtual Key**: Confirm a Chat Virtual Key is set (Admin > Settings) and that the selected model is on its allowlist.`;

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
        onChangeTab={setActiveTab}
      />

      {/* Persistent Flex Row Wrapper */}
      <div className="flex-1 flex flex-row h-full min-w-0 relative">
        
        {activeTab === 'models' ? (
          <ModelsDirectory
            selectedModel={selectedModel}
            onChangeModel={handleModelChange}
            onRequestPaidFlow={handlePaidFlowPrompt}
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
