import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  X, 
  Copy, 
  Check, 
  Play, 
  Code, 
  FileText, 
  Eye, 
  EyeOff, 
  Maximize2, 
  Minimize2, 
  Download, 
  ExternalLink,
  Terminal,
  Layers,
  Sparkles
} from 'lucide-react';
import { Artifact } from '../types';
import CodeBlock from './CodeBlock';

interface ArtifactPanelProps {
  artifact: Artifact | null;
  isOpen: boolean;
  onClose: () => void;
}

export default function ArtifactPanel({ artifact, isOpen, onClose }: ArtifactPanelProps) {
  const [activeTab, setActiveTab] = useState<'code' | 'preview' | 'document'>('code');
  const [copied, setCopied] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Set default tab based on artifact type
  useEffect(() => {
    if (artifact) {
      if (artifact.type === 'preview' || artifact.language === 'html' || artifact.language === 'svg') {
        setActiveTab('preview');
      } else if (artifact.type === 'document' || artifact.language === 'markdown' || artifact.language === 'md') {
        setActiveTab('document');
      } else {
        setActiveTab('code');
      }
    }
  }, [artifact]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(artifact.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy: ', err);
    }
  };

  const handleDownload = () => {
    const ext = artifact.language === 'typescript' || artifact.language === 'ts' ? 'ts' :
                artifact.language === 'tsx' ? 'tsx' :
                artifact.language === 'javascript' || artifact.language === 'js' ? 'js' :
                artifact.language === 'html' ? 'html' : 'txt';
    const blob = new Blob([artifact.code], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.title.toLowerCase().replace(/\s+/g, '_')}.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Generate a fully valid HTML file with styles and inject into an iframe
  const getIframeSrc = () => {
    if (!artifact) return '';
    
    let htmlContent = artifact.code;
    
    // If it is just an SVG, wrap it nicely
    if (artifact.language === 'svg' || htmlContent.trim().startsWith('<svg')) {
      htmlContent = `
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body {
              margin: 0;
              height: 100vh;
              display: flex;
              align-items: center;
              justify-content: center;
              background-color: #171716;
              color: #e0e0e0;
              font-family: sans-serif;
            }
            svg {
              max-width: 90%;
              max-height: 90%;
            }
          </style>
        </head>
        <body>
          ${artifact.code}
        </body>
        </html>
      `;
    } else if (!htmlContent.toLowerCase().includes('<html')) {
      // Wrap generic code in Tailwind block if it has Tailwind markup, or simple CSS setup
      htmlContent = `
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
          <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
          <style>
            body {
              background-color: #1b1b19;
              color: #e0e0e0;
              font-family: 'Inter', sans-serif;
              padding: 2rem;
              margin: 0;
            }
          </style>
        </head>
        <body>
          ${artifact.code}
        </body>
        </html>
      `;
    }

    const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
    return URL.createObjectURL(blob);
  };

  const iframeUrl = activeTab === 'preview' ? getIframeSrc() : '';

  // Clean up Object URL to prevent leaks
  useEffect(() => {
    return () => {
      if (iframeUrl) {
        URL.revokeObjectURL(iframeUrl);
      }
    };
  }, [iframeUrl]);

  if (!artifact) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ x: '100%', opacity: 0.8 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: '100%', opacity: 0.8 }}
          transition={{ type: 'spring', damping: 25, stiffness: 180 }}
          className={`${
            isFullscreen
              ? 'fixed inset-0 w-screen h-screen z-50'
              : 'fixed inset-y-0 right-0 w-full md:w-[600px] lg:relative lg:inset-auto lg:h-full lg:w-[500px] xl:w-[680px] z-40'
          } bg-[#0A0E14] border-l border-white/[0.08] flex flex-col shadow-2xl transition-all duration-300`}
          style={{ height: '100vh' }}
        >
          {/* Header Panel */}
          <div className="h-14 px-5 border-b border-white/[0.08] flex items-center justify-between bg-[#080d14]/80 backdrop-blur-md shrink-0">
            <div className="flex items-center space-x-3 min-w-0">
              <div className="w-8 h-8 rounded-[2px] bg-white/5 border border-white/10 flex items-center justify-center shrink-0">
                <Layers size={15} className="text-white/70" />
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-mono font-medium text-white/40 uppercase tracking-widest leading-none">
                  Workspace Artifact
                </span>
                <span className="text-sm font-medium text-white/90 truncate mt-1">
                  {artifact.title}
                </span>
              </div>
            </div>

            <div className="flex items-center space-x-2 shrink-0">
              {/* Copy Code */}
              <button
                onClick={handleCopy}
                className="p-1.5 text-white/50 hover:text-white hover:bg-white/5 rounded-[2px] border border-transparent hover:border-white/[0.06] transition-all cursor-pointer"
                title="Copy contents"
              >
                {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
              </button>

              {/* Download */}
              <button
                onClick={handleDownload}
                className="p-1.5 text-white/50 hover:text-white hover:bg-white/5 rounded-[2px] border border-transparent hover:border-white/[0.06] transition-all cursor-pointer"
                title="Download Source Code"
              >
                <Download size={14} />
              </button>

              {/* Toggle fullscreen */}
              <button
                onClick={() => setIsFullscreen(!isFullscreen)}
                className="p-1.5 text-white/50 hover:text-white hover:bg-white/5 rounded-[2px] border border-transparent hover:border-white/[0.06] transition-all cursor-pointer"
                title={isFullscreen ? "Exit Fullscreen" : "Fullscreen Workspace"}
              >
                {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              </button>

              <div className="h-4 w-[1px] bg-white/[0.08] mx-1" />

              {/* Close */}
              <button
                onClick={onClose}
                className="p-1.5 text-white/50 hover:text-white hover:bg-white/5 rounded-[2px] border border-transparent hover:border-white/[0.06] transition-all cursor-pointer"
                title="Close Artifact panel"
              >
                <X size={15} />
              </button>
            </div>
          </div>

          {/* Tab Selector & Actions */}
          <div className="h-11 px-5 border-b border-white/[0.05] bg-[#060a0f] flex items-center justify-between shrink-0 select-none">
            <div className="flex space-x-1">
              <button
                onClick={() => setActiveTab('code')}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-[2px] text-xs font-mono font-bold transition-all cursor-pointer ${
                  activeTab === 'code' 
                    ? 'bg-white/10 text-white' 
                    : 'text-white/50 hover:text-white hover:bg-white/[0.03]'
                }`}
              >
                <Code size={13} />
                <span>Code</span>
              </button>

              {(artifact.type === 'preview' || artifact.language === 'html' || artifact.language === 'svg') && (
                <button
                  onClick={() => {
                    setActiveTab('preview');
                    setPreviewKey(prev => prev + 1);
                  }}
                  className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-[2px] text-xs font-mono font-bold transition-all cursor-pointer ${
                    activeTab === 'preview' 
                      ? 'bg-white/10 text-white' 
                      : 'text-white/50 hover:text-white hover:bg-white/[0.03]'
                  }`}
                >
                  <Eye size={13} />
                  <span>Interactive Preview</span>
                </button>
              )}

              {(artifact.type === 'document' || artifact.language === 'markdown' || artifact.language === 'md') && (
                <button
                  onClick={() => setActiveTab('document')}
                  className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-[2px] text-xs font-mono font-bold transition-all cursor-pointer ${
                    activeTab === 'document' 
                      ? 'bg-white/10 text-white' 
                      : 'text-white/50 hover:text-white hover:bg-white/[0.03]'
                  }`}
                >
                  <FileText size={13} />
                  <span>Document View</span>
                </button>
              )}
            </div>

            {activeTab === 'preview' && (
              <button
                onClick={() => setPreviewKey(prev => prev + 1)}
                className="flex items-center space-x-1 px-2.5 py-1 text-[10px] font-mono font-bold text-white/50 hover:text-white hover:bg-white/5 border border-white/[0.06] rounded-[2px] transition-all cursor-pointer"
              >
                <Play size={11} className="text-emerald-400" />
                <span>Hot Reload</span>
              </button>
            )}
          </div>

          {/* Panel Viewport */}
          <div className="flex-grow overflow-auto bg-[#1b1b19] relative">
            <AnimatePresence mode="wait">
              {activeTab === 'code' && (
                <motion.div
                  key="code"
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -5 }}
                  transition={{ duration: 0.15 }}
                  className="p-5 max-w-full"
                >
                  <CodeBlock language={artifact.language} value={artifact.code} />
                </motion.div>
              )}

              {activeTab === 'preview' && (
                <motion.div
                  key={`preview-${previewKey}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="w-full h-full bg-[#1b1b19] relative"
                >
                  <iframe
                    ref={iframeRef}
                    src={iframeUrl}
                    title="Live Sandboxed Preview"
                    className="w-full h-full border-none bg-transparent"
                    sandbox="allow-scripts allow-modals"
                    referrerPolicy="no-referrer"
                  />
                </motion.div>
              )}

              {activeTab === 'document' && (
                <motion.div
                  key="document"
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -5 }}
                  transition={{ duration: 0.15 }}
                  className="p-8 max-w-2xl mx-auto text-[#e0e0e0] leading-relaxed select-text"
                >
                  <div className="flex items-center space-x-2 text-rose-300/80 mb-4 select-none">
                    <Sparkles size={14} />
                    <span className="text-xs font-mono uppercase tracking-widest font-semibold">Synthesized Prose</span>
                  </div>
                  <h1 className="text-2xl font-bold font-sans tracking-tight mb-6 text-white border-b border-white/[0.08] pb-3">
                    {artifact.title}
                  </h1>
                  <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed prose-li:my-1 text-white/95 whitespace-pre-wrap font-sans font-light">
                    {artifact.code}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
