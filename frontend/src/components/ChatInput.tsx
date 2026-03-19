import { useState, useRef, type KeyboardEvent, type FormEvent } from 'react';

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
}

export default function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!value.trim() || isLoading) return;
    onSend(value);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as FormEvent);
    }
  }

  function handleInput() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  return (
    <div className="px-4 pb-4 pt-3 border-t border-[#2e2e2e] bg-[#0f0f0f]">
      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-3 bg-[#1e1e1e] border border-[#2e2e2e] rounded-2xl px-4 py-3 focus-within:border-[#444] transition-colors"
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          disabled={isLoading}
          placeholder="Ask anything about Formula One…"
          rows={1}
          className="flex-1 bg-transparent text-gray-200 placeholder-gray-600 text-sm resize-none outline-none leading-relaxed max-h-40 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!value.trim() || isLoading}
          className="flex-shrink-0 w-8 h-8 rounded-xl bg-[#e10600] hover:bg-[#b30500] disabled:bg-[#3a1a1a] disabled:text-gray-600 text-white transition-colors flex items-center justify-center cursor-pointer disabled:cursor-not-allowed"
          aria-label="Send message"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </form>
      <p className="text-center text-gray-700 text-xs mt-2">
        Press <kbd className="px-1 py-0.5 rounded bg-[#2a2a2a] text-gray-500 text-xs font-mono">Enter</kbd> to send · <kbd className="px-1 py-0.5 rounded bg-[#2a2a2a] text-gray-500 text-xs font-mono">Shift+Enter</kbd> for new line
      </p>
    </div>
  );
}
