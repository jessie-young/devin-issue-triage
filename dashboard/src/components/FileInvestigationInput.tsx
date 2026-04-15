import { useState } from 'react';
import { Send, Plus, X } from 'lucide-react';

interface FileInvestigationInputProps {
  onFile: (input: string) => void;
}

export function FileInvestigationInput({ onFile }: FileInvestigationInputProps) {
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
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-app-border
          bg-white hover:bg-app-panel text-xs font-medium text-app-text-secondary
          hover:text-app-text transition-all shadow-sm"
      >
        <Plus className="w-3.5 h-3.5" />
        Add Issue
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
        className="px-3 py-1.5 rounded-lg border border-app-border bg-white
          text-xs text-app-text placeholder-app-text-muted
          focus:outline-none focus:ring-2 focus:ring-app-primary/20 focus:border-app-primary w-64"
      />
      <button
        type="submit"
        disabled={!input.trim()}
        className="flex items-center gap-1 px-3 py-1.5 rounded-lg
          bg-app-primary text-xs font-medium text-white
          hover:bg-app-primary-hover disabled:opacity-30 disabled:cursor-not-allowed transition-all"
      >
        <Send className="w-3 h-3" />
        Submit
      </button>
      <button
        type="button"
        onClick={() => { setIsOpen(false); setInput(''); }}
        className="p-1.5 rounded-lg text-app-text-muted hover:text-app-text hover:bg-app-panel transition-all"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </form>
  );
}
