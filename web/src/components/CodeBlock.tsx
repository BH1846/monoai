import React, { useState } from 'react';
import { 
  Terminal, 
  FileCode, 
  Cpu, 
  Braces, 
  Code, 
  Database, 
  Globe, 
  Hash, 
  Copy, 
  Check,
  ExternalLink
} from 'lucide-react';

interface CodeBlockProps {
  language: string;
  value: string;
  onOpenInArtifact?: (title: string, language: string, code: string, type: 'code' | 'preview' | 'document') => void;
}

function getLanguageMeta(lang: string) {
  const l = lang.toLowerCase();
  switch (l) {
    case 'javascript':
    case 'js':
      return { name: 'JavaScript', icon: FileCode, color: 'text-amber-400' };
    case 'typescript':
    case 'ts':
      return { name: 'TypeScript', icon: FileCode, color: 'text-blue-400' };
    case 'tsx':
    case 'jsx':
      return { name: 'React TSX', icon: Code, color: 'text-cyan-400' };
    case 'python':
    case 'py':
      return { name: 'Python', icon: Cpu, color: 'text-emerald-400' };
    case 'html':
      return { name: 'HTML', icon: Globe, color: 'text-orange-400' };
    case 'css':
      return { name: 'CSS', icon: Hash, color: 'text-pink-400' };
    case 'rust':
    case 'rs':
      return { name: 'Rust', icon: Cpu, color: 'text-orange-500' };
    case 'go':
    case 'golang':
      return { name: 'Go', icon: Terminal, color: 'text-sky-400' };
    case 'bash':
    case 'sh':
    case 'shell':
    case 'zsh':
      return { name: 'Shell', icon: Terminal, color: 'text-zinc-400' };
    case 'sql':
    case 'postgres':
    case 'sqlite':
    case 'mysql':
      return { name: 'SQL', icon: Database, color: 'text-indigo-400' };
    case 'json':
      return { name: 'JSON', icon: Braces, color: 'text-purple-400' };
    default:
      return { name: lang.toUpperCase(), icon: Code, color: 'text-white/50' };
  }
}

export default function CodeBlock({ language, value, onOpenInArtifact }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const meta = getLanguageMeta(language);
  const IconComponent = meta.icon;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code: ', err);
    }
  };

  const getHighlightedHtml = (raw: string, lang: string) => {
    // Escape HTML to prevent XSS
    let escaped = raw
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Universal highlighting patterns
    const commentRegex = /(\/\/.*|#.*|\/\*[\s\S]*?\*\/)/g;
    const stringRegex = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)/g;
    const numberRegex = /\b(\d+)\b/g;
    
    let keywords: string[] = [];
    const lowerLang = lang.toLowerCase();
    
    if (['js', 'javascript', 'ts', 'typescript', 'tsx', 'jsx'].includes(lowerLang)) {
      keywords = ['import', 'export', 'from', 'const', 'let', 'var', 'function', 'class', 'return', 'if', 'else', 'for', 'while', 'await', 'async', 'try', 'catch', 'new', 'this', 'interface', 'type', 'extends', 'default', 'null', 'undefined', 'true', 'false'];
    } else if (['py', 'python'].includes(lowerLang)) {
      keywords = ['def', 'class', 'import', 'from', 'return', 'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'as', 'with', 'lambda', 'print', 'in', 'is', 'not', 'and', 'or', 'None', 'True', 'False'];
    } else if (['go', 'golang'].includes(lowerLang)) {
      keywords = ['package', 'import', 'func', 'var', 'const', 'type', 'struct', 'interface', 'return', 'if', 'else', 'for', 'range', 'go', 'select', 'chan', 'defer', 'true', 'false', 'nil'];
    } else if (['rs', 'rust'].includes(lowerLang)) {
      keywords = ['fn', 'let', 'mut', 'use', 'mod', 'struct', 'enum', 'impl', 'trait', 'return', 'if', 'else', 'match', 'for', 'while', 'pub', 'async', 'await', 'true', 'false'];
    } else if (['bash', 'sh', 'shell'].includes(lowerLang)) {
      keywords = ['if', 'then', 'else', 'elif', 'fi', 'for', 'in', 'do', 'done', 'while', 'echo', 'exit', 'return', 'local', 'function'];
    } else if (['sql'].includes(lowerLang)) {
      keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'ON', 'GROUP', 'BY', 'ORDER', 'HAVING', 'LIMIT', 'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE', 'CREATE', 'TABLE', 'ALTER', 'DROP', 'INDEX', 'PRIMARY', 'KEY', 'FOREIGN', 'AND', 'OR', 'NOT', 'IN', 'IS', 'NULL', 'as', 'select', 'from', 'where', 'join', 'group', 'by', 'order', 'insert', 'update', 'delete'];
    }

    const placeholders: string[] = [];
    
    // Protect Comments
    escaped = escaped.replace(commentRegex, (match) => {
      placeholders.push(`<span class="text-white/40 italic font-light">${match}</span>`);
      return `___PLACEHOLDER_${placeholders.length - 1}___`;
    });

    // Protect Strings
    escaped = escaped.replace(stringRegex, (match) => {
      placeholders.push(`<span class="text-amber-200/95">${match}</span>`);
      return `___PLACEHOLDER_${placeholders.length - 1}___`;
    });

    // Protect Keywords
    if (keywords.length > 0) {
      const keywordRegex = new RegExp(`\\b(${keywords.join('|')})\\b`, 'g');
      escaped = escaped.replace(keywordRegex, (match) => {
        return `<span class="text-rose-400 font-medium">${match}</span>`;
      });
    }

    // Protect Numbers
    escaped = escaped.replace(numberRegex, (match) => {
      return `<span class="text-indigo-300">${match}</span>`;
    });

    // Restore placeholders
    for (let i = placeholders.length - 1; i >= 0; i--) {
      escaped = escaped.replace(`___PLACEHOLDER_${i}___`, placeholders[i]);
    }

    return escaped;
  };

  return (
    <div className="w-full my-5 overflow-hidden rounded-[2px] border border-white/[0.08] bg-[#0c121a] shadow-lg flex flex-col font-mono animate-fadeIn">
      {/* Code Block Header */}
      <div className="h-10 px-4 bg-[#080d14] border-b border-white/[0.06] flex items-center justify-between select-none shrink-0">
        <div className="flex items-center space-x-2">
          <IconComponent size={14} className={`${meta.color} shrink-0`} />
          <span className="text-xs font-mono font-medium tracking-wide text-white/70">
            {meta.name}
          </span>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={handleCopy}
            className="flex items-center space-x-1.5 px-2 py-1 rounded bg-white/0 hover:bg-white/5 border border-transparent hover:border-white/5 text-[11px] text-white/50 hover:text-white transition-all cursor-pointer focus:outline-none"
          >
            {copied ? (
              <>
                <Check size={11} className="text-emerald-400 shrink-0" />
                <span className="text-emerald-400 font-medium">Copied!</span>
              </>
            ) : (
              <>
                <Copy size={11} className="shrink-0" />
                <span>Copy code</span>
              </>
            )}
          </button>

          {onOpenInArtifact && (
            <button
              onClick={() => {
                const title = `Snippet (${meta.name})`;
                const type = ['html', 'svg'].includes(language.toLowerCase()) ? 'preview' : 'code';
                onOpenInArtifact(title, language, value, type);
              }}
              className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] hover:border-white/[0.12] text-[11px] text-white/80 hover:text-white transition-all cursor-pointer focus:outline-none font-medium"
              title="Open inside the workspace panel"
            >
              <ExternalLink size={11} className="shrink-0" />
              <span>Workspace</span>
            </button>
          )}
        </div>
      </div>

      {/* Code viewport with line numbers and highlighting */}
      <div className="overflow-x-auto w-full bg-[#060a0f] p-4">
        <pre className="font-mono text-[12px] leading-relaxed text-white/85 selection:bg-white/10">
          <code dangerouslySetInnerHTML={{ __html: getHighlightedHtml(value, language) }} />
        </pre>
      </div>
    </div>
  );
}
