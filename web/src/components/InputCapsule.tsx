import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Plus,
  ChevronDown,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  ArrowUp,
  X,
  File,
  Image as ImageIcon,
  Check
} from 'lucide-react';
import { Attachment, ModelType, ModelOption, ModelRecord } from '../types';
import { ENTERPRISE_MODELS } from '../data/models';
import { useGateway } from '../context/GatewayContext';

interface InputCapsuleProps {
  onSendMessage: (content: string, attachments: Attachment[]) => void;
  selectedModel: ModelType;
  onChangeModel: (model: ModelType) => void;
  isLoading: boolean;
  onRequestPaidFlow: () => void;
  suggestionText?: string;
  onSuggestionTextConsumed?: () => void;
}

export default function InputCapsule({
  onSendMessage,
  selectedModel,
  onChangeModel,
  isLoading,
  onRequestPaidFlow,
  suggestionText = '',
  onSuggestionTextConsumed
}: InputCapsuleProps) {
  const [content, setContent] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [micActive, setMicActive] = useState(false);
  const [audioOutActive, setAudioOutActive] = useState(true);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { config, adminFetch, modelAllowlist } = useGateway();
  const [registeredModels, setRegisteredModels] = useState<ModelOption[]>([]);

  // Populate the model picker from the gateway's live provider/model registry
  // (Providers tab) instead of the static mock catalog -- only "auto" from
  // that catalog is retained.
  useEffect(() => {
    let cancelled = false;
    if (!config.adminKey) {
      setRegisteredModels([]);
      return;
    }
    adminFetch('models')
      .then(async (res) => {
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (cancelled) return;
        const opts: ModelOption[] = (data.models || []).map((m: ModelRecord) => ({
          id: m.model_id,
          name: m.display_name || m.model_id,
          tag: m.provider_name,
          description: `Routed to "${m.upstream_model}" via registered provider "${m.provider_name}".`,
          isPaid: false,
          provider: 'Enterprise',
          latency: '—',
          costPerMillion: '—',
          contextWindow: '—',
          guardrails: ['Gateway-enforced policy (PII / secrets / RBAC)'],
          status: m.enabled ? 'Approved' : 'Restricted',
        }));
        setRegisteredModels(opts);
      })
      .catch(() => setRegisteredModels([]));
    return () => {
      cancelled = true;
    };
  }, [config.adminKey, adminFetch]);

  // Handle suggestion selection from parent
  useEffect(() => {
    if (suggestionText) {
      setContent(suggestionText);
      onSuggestionTextConsumed?.();
      // Focus textarea
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }
  }, [suggestionText, onSuggestionTextConsumed]);

  const autoOption = ENTERPRISE_MODELS.find(m => m.id === 'auto')!;
  // The active virtual key's model_allowlist (GET /v1/me), when set by an
  // admin, restricts which gateways this session is even allowed to call --
  // filter the picker to match so it never offers something the gateway
  // would reject with model_not_allowed.
  const models = useMemo(() => {
    const all = [autoOption, ...registeredModels];
    return modelAllowlist ? all.filter(m => modelAllowlist.includes(m.id)) : all;
  }, [registeredModels, modelAllowlist]);

  // If the currently selected model falls out of the allowed set (allowlist
  // just loaded/changed, or the model was deleted), correct the *real*
  // selection, not just its on-screen label -- otherwise the dropdown shows
  // a fallback model while the request that actually goes out still carries
  // the old, now-disallowed model id.
  useEffect(() => {
    if (models.length > 0 && !models.some(m => m.id === selectedModel)) {
      onChangeModel(models[0].id);
    }
  }, [models, selectedModel, onChangeModel]);

  const activeModelObj = models.find(m => m.id === selectedModel) || models[0] || autoOption;

  // Auto-resize text area as lines are typed
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [content]);

  // Handle dropdown outside clicks
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowModelDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSend = () => {
    if (isLoading) return;
    if (!content.trim() && attachments.length === 0) return;
    
    onSendMessage(content, attachments);
    setContent('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Convert File object to local attachment format
  const processFiles = (fileList: FileList) => {
    Array.from(fileList).forEach(file => {
      const reader = new FileReader();

      // Setup standard properties
      const id = Math.random().toString(36).substring(7);
      const sizeFormatted = file.size > 1024 * 1024 
        ? `${(file.size / (1024 * 1024)).toFixed(1)} MB` 
        : `${(file.size / 1024).toFixed(0)} KB`;

      if (file.type.startsWith('image/')) {
        reader.onloadend = () => {
          setAttachments(prev => [...prev, {
            id,
            name: file.name,
            size: sizeFormatted,
            type: file.type,
            base64: reader.result as string,
            url: URL.createObjectURL(file)
          }]);
        };
        reader.readAsDataURL(file);
      } else {
        // Assume text / document file
        reader.onloadend = () => {
          setAttachments(prev => [...prev, {
            id,
            name: file.name,
            size: sizeFormatted,
            type: file.type,
            text: reader.result as string,
            url: URL.createObjectURL(file)
          }]);
        };
        reader.readAsText(file);
      }
    });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments(prev => prev.filter(att => att.id !== id));
  };

  const selectModelOption = (opt: ModelOption) => {
    if (opt.isPaid) {
      // Trigger paywall/API key flow
      onRequestPaidFlow();
    }
    onChangeModel(opt.id);
    setShowModelDropdown(false);
  };

  return (
    <div 
      className="shrink-0 p-6 bg-gradient-to-t from-[#0A0E14] via-[#0A0E14] to-transparent relative"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="max-w-3xl mx-auto relative">
        
        {/* Drag Over Overlay Alert */}
        {isDragging && (
          <div className="absolute inset-0 bg-[#0c121a]/95 border-2 border-dashed border-white/20 rounded-[2px] flex items-center justify-center space-x-3 z-30 animate-pulse">
            <Plus size={20} className="text-white/80" />
            <span className="text-sm text-white/80 font-medium">Drop your datasets or files to attach...</span>
          </div>
        )}

        {/* Panel C rounded container */}
        <div className="bg-[#0c121a] border border-white/[0.08] rounded-[2px] shadow-2xl flex flex-col focus-within:border-white/20 transition-all">
          
          {/* Pending Attachments Deck inside the capsule */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2.5 p-3.5 border-b border-white/[0.08] bg-[#0c121a]/50 rounded-t-[2px]">
              {attachments.map((att) => (
                <div 
                  key={att.id}
                  className="flex items-center space-x-2 bg-white/5 border border-white/[0.08] pl-2 pr-1.5 py-1 rounded-[1px] text-xs relative group"
                >
                  {att.type.startsWith('image/') && att.base64 ? (
                    <img 
                      src={att.base64} 
                      alt={att.name} 
                      className="w-5 h-5 object-cover rounded-[1px] border border-white/10"
                    />
                  ) : (
                    <File size={13} className="text-white/60 shrink-0" />
                  )}
                  <div className="flex flex-col min-w-0 pr-1.5 font-mono">
                    <span className="text-[11px] font-medium text-white/90 truncate max-w-[120px]">{att.name}</span>
                    <span className="text-[9px] text-white/40 font-mono">{att.size}</span>
                  </div>
                  <button
                    onClick={() => removeAttachment(att.id)}
                    className="p-0.5 hover:bg-white/10 rounded-[1px] text-white/40 hover:text-white transition-all shrink-0"
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Top Half: Text Input Area */}
          <div className="pt-3 px-4 pb-1">
            <textarea
              ref={textareaRef}
              rows={1}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Write a message..."
              className="w-full bg-transparent border-none text-white/95 placeholder-white/20 text-sm focus:outline-none resize-none min-h-[24px] max-h-[180px] leading-relaxed py-1"
            />
          </div>

          {/* Bottom Row Utilities */}
          <div className="h-11 px-4 flex items-center justify-between border-t border-white/[0.08] select-none">
            
            {/* Left side attachment button */}
            <div className="flex items-center">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="w-7 h-7 bg-white/5 hover:bg-white/10 text-white/70 hover:text-white rounded-[2px] flex items-center justify-center transition-all cursor-pointer border border-white/[0.04]"
                title="Attach file (PDF, TXT, JSON, Code, ZIP, images)"
              >
                <Plus size={14} />
              </button>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                multiple
                className="hidden"
                accept="image/*,application/pdf,text/*,application/zip,.zip"
              />
            </div>

            {/* Right side interaction cluster */}
            <div className="flex items-center space-x-2">
              
              {/* Audio Out speaker state toggle */}
              <button
                onClick={() => setAudioOutActive(!audioOutActive)}
                className={`p-1.5 rounded-[1px] transition-all ${
                  audioOutActive 
                    ? 'text-white/50 hover:text-white hover:bg-white/5' 
                    : 'text-red-400 bg-red-400/5 hover:bg-red-400/10'
                }`}
                title={audioOutActive ? "Voice response enabled" : "Voice response muted"}
              >
                {audioOutActive ? <Volume2 size={14} /> : <VolumeX size={14} />}
              </button>

              {/* Mic state toggle */}
              <button
                onClick={() => setMicActive(!micActive)}
                className={`p-1.5 rounded-[1px] transition-all ${
                  micActive 
                    ? 'text-emerald-400 bg-emerald-400/5 hover:bg-emerald-400/10 animate-pulse' 
                    : 'text-white/50 hover:text-white hover:bg-white/5'
                }`}
                title={micActive ? "Microphone listening..." : "Microphone disabled"}
              >
                {micActive ? <Mic size={14} /> : <MicOff size={14} />}
              </button>

              <span className="w-px h-4 bg-white/10" />

              {/* Model Selector dropdown trigger */}
              <div className="relative" ref={dropdownRef}>
                <button
                  type="button"
                  onClick={() => setShowModelDropdown(!showModelDropdown)}
                  className="flex items-center space-x-1.5 px-2.5 py-1 bg-white/5 hover:bg-white/10 border border-white/[0.08] rounded-[2px] text-[11px] font-medium transition-all cursor-pointer animate-fadeIn"
                  title="Select AI Model"
                >
                  <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full shrink-0 animate-pulse"></span>
                  <span className="text-white/80 font-mono tracking-wide">{activeModelObj.name}</span>
                  <ChevronDown size={10} className="text-white/40 mt-0.5" />
                </button>

                {/* Model dropdown overlay */}
                {showModelDropdown && (
                  <div className="absolute right-0 bottom-full mb-2 w-80 bg-[#0c121a] border border-rose-500/20 rounded-[2px] shadow-2xl py-1.5 z-40 animate-fadeIn animate-duration-150">
                    <div className="px-3.5 py-1.5 border-b border-white/[0.06] flex items-center justify-between">
                      <span className="text-[9px] font-mono text-white/40 uppercase tracking-widest font-bold">Gateway Destination</span>
                      <span className="text-[9px] font-mono text-rose-400 font-bold px-1.5 py-0.5 bg-rose-500/10 rounded-[1px]">SHIELD ACTIVE</span>
                    </div>
                    <div className="max-h-72 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/5">
                      {models.map((opt) => (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => selectModelOption(opt)}
                          className="flex flex-col text-left w-full px-3.5 py-2.5 hover:bg-white/5 transition-colors group"
                        >
                          <div className="flex items-center justify-between w-full font-mono">
                            <div className="flex items-center space-x-2">
                              <span className="text-xs font-semibold text-white/95 group-hover:text-white">{opt.name}</span>
                              <span className="text-[9px] font-mono px-1.5 py-0.2 bg-white/10 text-white/60 rounded-[1px]">
                                {opt.tag}
                              </span>
                            </div>
                            {selectedModel === opt.id && (
                              <Check size={12} className="text-emerald-400" />
                            )}
                          </div>
                          <p className="text-[10px] text-white/45 leading-relaxed mt-1 font-sans">{opt.description}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Rounded Submit Action */}
              <button
                onClick={handleSend}
                disabled={isLoading || (!content.trim() && attachments.length === 0)}
                className={`w-7 h-7 rounded-[2px] flex items-center justify-center transition-all ${
                  isLoading || (!content.trim() && attachments.length === 0)
                    ? 'bg-white/5 text-white/20 border border-white/[0.02] cursor-not-allowed'
                    : 'bg-white hover:bg-white/90 text-[#191919] cursor-pointer shadow-lg'
                }`}
                title="Send message"
              >
                <ArrowUp size={13} className="stroke-[2.5px]" />
              </button>

            </div>

          </div>

        </div>

        {/* Small warning disclaimer */}
        <p className="text-center text-[9px] font-mono text-white/20 mt-2 tracking-wide uppercase">
          MonoAI can make mistakes. Verify critical system schemas.
        </p>

      </div>
    </div>
  );
}
