import { useState } from 'react';
import { Send, Plus } from 'lucide-react';

interface FileMissionInputProps {
  onFile: (input: string) => void;
}

export function FileMissionInput({ onFile }: FileMissionInputProps) {
  const [input, setInput] = useState('');
  const [isOpen, setIsOpen] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    onFile(input.trim());
    setInput('');
    setIsOpen(false);
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-nasa-border
          bg-nasa-panel hover:bg-nasa-panel/80 text-xs font-mono text-nasa-cyan
          hover:border-nasa-cyan/50 transition-all"
      >
        <Plus className="w-3.5 h-3.5" />
        FILE MISSION
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Issue URL or number..."
        autoFocus
        className="px-3 py-1.5 rounded border border-nasa-border bg-nasa-navy
          text-xs font-mono text-nasa-text placeholder-nasa-muted/40
          focus:outline-none focus:border-nasa-cyan/50 w-64"
      />
      <button
        type="submit"
        disabled={!input.trim()}
        className="flex items-center gap-1 px-3 py-1.5 rounded border border-nasa-cyan/40
          bg-nasa-cyan/10 text-xs font-mono text-nasa-cyan
          hover:bg-nasa-cyan/20 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
      >
        <Send className="w-3 h-3" />
        SEND
      </button>
      <button
        type="button"
        onClick={() => { setIsOpen(false); setInput(''); }}
        className="text-xs font-mono text-nasa-muted hover:text-nasa-text px-2 py-1.5"
      >
        ESC
      </button>
    </form>
  );
}
