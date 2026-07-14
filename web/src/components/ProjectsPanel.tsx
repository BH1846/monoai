import React, { useState } from 'react';
import {
  FolderKanban, Plus, ArrowLeft, MessageSquarePlus, Trash2, Pencil,
  Check, X, Sparkles, Clock
} from 'lucide-react';
import { Project, ChatSession } from '../types';

interface ProjectsPanelProps {
  projects: Project[];
  sessions: ChatSession[];
  selectedProjectId: string | null;
  onSelectProject: (id: string | null) => void;
  onCreateProject: (name: string, description: string) => string;
  onUpdateProject: (id: string, patch: Partial<Project>) => void;
  onDeleteProject: (id: string) => void;
  onOpenChat: (sessionId: string) => void;
  onNewChatInProject: (projectId: string) => void;
}

const PROJECT_COLORS = ['#c2703f', '#4f7cc2', '#5fae7a', '#a664c2', '#c25f8f', '#c2a83f'];

function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs > 1 ? 's' : ''} ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`;
  return new Date(ts).toLocaleDateString();
}

export default function ProjectsPanel({
  projects,
  sessions,
  selectedProjectId,
  onSelectProject,
  onCreateProject,
  onUpdateProject,
  onDeleteProject,
  onOpenChat,
  onNewChatInProject,
}: ProjectsPanelProps) {
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [editingInstructions, setEditingInstructions] = useState(false);
  const [instructionsDraft, setInstructionsDraft] = useState('');

  const selectedProject = projects.find((p) => p.id === selectedProjectId) || null;
  const projectChats = (pid: string) => sessions.filter((s) => s.projectId === pid);
  const projectColor = (p: Project) => p.color || PROJECT_COLORS[0];

  const submitCreate = () => {
    if (!newName.trim()) return;
    const id = onCreateProject(newName.trim(), newDesc.trim());
    setNewName('');
    setNewDesc('');
    setCreating(false);
    onSelectProject(id);
  };

  // ---- Project detail view ----
  if (selectedProject) {
    const chats = projectChats(selectedProject.id);
    return (
      <div className="flex-1 flex flex-col h-full bg-[#0A0E14] text-white overflow-y-auto">
        <div className="max-w-4xl w-full mx-auto px-6 md:px-10 py-8 space-y-8">
          {/* Header */}
          <div className="space-y-4">
            <button
              onClick={() => onSelectProject(null)}
              className="flex items-center space-x-1.5 text-xs text-white/50 hover:text-white/90 transition-colors cursor-pointer"
            >
              <ArrowLeft size={14} />
              <span>All projects</span>
            </button>
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start space-x-3.5">
                <div
                  className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0 mt-0.5"
                  style={{ backgroundColor: `${projectColor(selectedProject)}22`, border: `1px solid ${projectColor(selectedProject)}55` }}
                >
                  <FolderKanban size={20} style={{ color: projectColor(selectedProject) }} />
                </div>
                <div className="space-y-1">
                  <h1 className="text-2xl font-semibold tracking-tight">{selectedProject.name}</h1>
                  {selectedProject.description && (
                    <p className="text-sm text-white/50 leading-relaxed max-w-2xl">{selectedProject.description}</p>
                  )}
                </div>
              </div>
              <button
                onClick={() => {
                  if (window.confirm(`Delete project "${selectedProject.name}"? Chats inside it are kept but detached.`)) {
                    onDeleteProject(selectedProject.id);
                  }
                }}
                className="shrink-0 p-2 text-white/30 hover:text-rose-400 hover:bg-rose-500/5 rounded-md transition-colors cursor-pointer"
                title="Delete project"
              >
                <Trash2 size={15} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: chats in project */}
            <div className="lg:col-span-2 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-white/40">Chats in this project</h2>
                <button
                  onClick={() => onNewChatInProject(selectedProject.id)}
                  className="flex items-center space-x-1.5 px-3 py-1.5 bg-white text-[#0A0E14] hover:bg-white/90 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                >
                  <MessageSquarePlus size={13} />
                  <span>New chat</span>
                </button>
              </div>

              {chats.length === 0 ? (
                <div className="border border-dashed border-white/10 rounded-xl py-12 px-6 text-center space-y-2">
                  <Sparkles className="mx-auto text-white/20" size={22} />
                  <p className="text-sm text-white/40">No chats yet in this project.</p>
                  <p className="text-xs text-white/25">Start a chat and it'll use this project's instructions.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {chats.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => onOpenChat(c.id)}
                      className="w-full text-left bg-[#0d1420] hover:bg-[#111a28] border border-white/[0.06] hover:border-white/[0.12] rounded-xl p-4 transition-all cursor-pointer group"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm text-white/90 font-medium truncate">{c.title || 'Untitled chat'}</span>
                        <span className="text-[10px] text-white/30 shrink-0">{c.messages.length} msg{c.messages.length !== 1 ? 's' : ''}</span>
                      </div>
                      {c.messages.length > 0 && (
                        <p className="text-xs text-white/40 mt-1 truncate">
                          {c.messages[c.messages.length - 1].content}
                        </p>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Right: project knowledge / instructions */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-white/40">Project instructions</h2>
                {!editingInstructions && (
                  <button
                    onClick={() => { setInstructionsDraft(selectedProject.instructions); setEditingInstructions(true); }}
                    className="p-1 text-white/40 hover:text-white/80 rounded transition-colors cursor-pointer"
                    title="Edit instructions"
                  >
                    <Pencil size={13} />
                  </button>
                )}
              </div>

              <div className="bg-[#0d1420] border border-white/[0.06] rounded-xl p-4">
                {editingInstructions ? (
                  <div className="space-y-2">
                    <textarea
                      autoFocus
                      value={instructionsDraft}
                      onChange={(e) => setInstructionsDraft(e.target.value)}
                      placeholder="Give the model context and preferences for every chat in this project — tone, role, formatting, domain knowledge…"
                      className="w-full h-40 bg-[#05080c] border border-white/10 focus:border-indigo-500/40 rounded-lg p-3 text-xs text-white/85 placeholder-white/25 focus:outline-none resize-none leading-relaxed"
                    />
                    <div className="flex justify-end space-x-2">
                      <button
                        onClick={() => setEditingInstructions(false)}
                        className="flex items-center space-x-1 px-2.5 py-1 text-xs text-white/50 hover:text-white/80 rounded-md transition-colors cursor-pointer"
                      >
                        <X size={12} /> <span>Cancel</span>
                      </button>
                      <button
                        onClick={() => { onUpdateProject(selectedProject.id, { instructions: instructionsDraft }); setEditingInstructions(false); }}
                        className="flex items-center space-x-1 px-2.5 py-1 text-xs bg-white text-[#0A0E14] hover:bg-white/90 rounded-md font-semibold transition-colors cursor-pointer"
                      >
                        <Check size={12} /> <span>Save</span>
                      </button>
                    </div>
                  </div>
                ) : selectedProject.instructions ? (
                  <p className="text-xs text-white/70 whitespace-pre-wrap leading-relaxed">{selectedProject.instructions}</p>
                ) : (
                  <p className="text-xs text-white/30 leading-relaxed">
                    No instructions yet. Add context the model should use for every chat in this project.
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ---- Projects grid (landing) ----
  return (
    <div className="flex-1 flex flex-col h-full bg-[#0A0E14] text-white overflow-y-auto">
      <div className="max-w-5xl w-full mx-auto px-6 md:px-10 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
            <p className="text-sm text-white/45">Group chats and give them shared instructions.</p>
          </div>
          <button
            onClick={() => setCreating(true)}
            className="flex items-center space-x-1.5 px-4 py-2 bg-white text-[#0A0E14] hover:bg-white/90 rounded-lg text-sm font-semibold transition-colors cursor-pointer"
          >
            <Plus size={15} />
            <span>New project</span>
          </button>
        </div>

        {creating && (
          <div className="bg-[#0d1420] border border-white/[0.08] rounded-xl p-5 space-y-3 animate-fadeIn">
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submitCreate(); }}
              placeholder="Project name"
              className="w-full bg-[#05080c] border border-white/10 focus:border-indigo-500/40 rounded-lg px-3 py-2 text-sm text-white/90 placeholder-white/25 focus:outline-none"
            />
            <input
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submitCreate(); }}
              placeholder="What's it for? (optional)"
              className="w-full bg-[#05080c] border border-white/10 focus:border-indigo-500/40 rounded-lg px-3 py-2 text-sm text-white/90 placeholder-white/25 focus:outline-none"
            />
            <div className="flex justify-end space-x-2">
              <button
                onClick={() => { setCreating(false); setNewName(''); setNewDesc(''); }}
                className="px-3 py-1.5 text-xs text-white/50 hover:text-white/80 rounded-md transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={submitCreate}
                disabled={!newName.trim()}
                className="px-3 py-1.5 text-xs bg-white text-[#0A0E14] hover:bg-white/90 rounded-md font-semibold transition-colors cursor-pointer disabled:opacity-40"
              >
                Create project
              </button>
            </div>
          </div>
        )}

        {projects.length === 0 && !creating ? (
          <div className="border border-dashed border-white/10 rounded-2xl py-20 px-6 text-center space-y-3">
            <div className="w-12 h-12 rounded-xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mx-auto">
              <FolderKanban className="text-white/30" size={24} />
            </div>
            <p className="text-sm text-white/50">No projects yet.</p>
            <button
              onClick={() => setCreating(true)}
              className="inline-flex items-center space-x-1.5 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm text-white/80 transition-colors cursor-pointer"
            >
              <Plus size={14} />
              <span>Create your first project</span>
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => {
              const count = projectChats(p.id).length;
              return (
                <button
                  key={p.id}
                  onClick={() => onSelectProject(p.id)}
                  className="text-left bg-[#0d1420] hover:bg-[#111a28] border border-white/[0.06] hover:border-white/[0.14] rounded-2xl p-5 transition-all cursor-pointer flex flex-col h-40 group"
                >
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center mb-3 shrink-0"
                    style={{ backgroundColor: `${projectColor(p)}22`, border: `1px solid ${projectColor(p)}55` }}
                  >
                    <FolderKanban size={18} style={{ color: projectColor(p) }} />
                  </div>
                  <div className="font-semibold text-white/90 truncate">{p.name}</div>
                  <div className="text-xs text-white/45 mt-1 line-clamp-2 flex-1 leading-relaxed">
                    {p.description || 'No description'}
                  </div>
                  <div className="flex items-center justify-between text-[10px] text-white/30 mt-3 font-mono">
                    <span>{count} chat{count !== 1 ? 's' : ''}</span>
                    <span className="flex items-center gap-1"><Clock size={9} /> {relativeTime(p.updatedAt)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
