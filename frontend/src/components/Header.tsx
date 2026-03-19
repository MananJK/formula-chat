export default function Header({ onClear, hasMessages }: { onClear: () => void; hasMessages: boolean }) {
  return (
    <header className="flex items-center justify-between px-6 py-4 border-b border-[#2e2e2e] bg-[#0f0f0f]">
      <div className="flex items-center gap-3">
        {/* F1 logo mark */}
        <div className="flex items-center gap-1.5">
          <div className="w-1 h-6 bg-[#e10600] rounded-sm" />
          <span className="text-white font-bold text-lg tracking-tight leading-none">
            F1
          </span>
          <div className="w-1 h-6 bg-[#e10600] rounded-sm" />
        </div>
        <div className="h-5 w-px bg-[#2e2e2e]" />
        <span className="text-gray-400 text-sm font-medium tracking-wide uppercase">
          Chatbot
        </span>
      </div>

      {hasMessages && (
        <button
          onClick={onClear}
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors px-3 py-1.5 rounded border border-[#2e2e2e] hover:border-[#444] cursor-pointer"
        >
          New chat
        </button>
      )}
    </header>
  );
}
