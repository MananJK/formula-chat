import type { Message } from '../types';

const TOOL_LABELS: Record<string, string> = {
  f1_knowledge: 'Searching knowledge base',
};

interface ChatMessageProps {
  message: Message;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-2">
        <div className="max-w-[75%] bg-[#e10600] text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed shadow-lg">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 px-4 py-2">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[#e10600] flex items-center justify-center shadow-md">
        <span className="text-white text-xs font-bold leading-none">F1</span>
      </div>
      <div className="flex flex-col gap-2 max-w-[80%]">
        <div
          className={[
            'rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed',
            message.error
              ? 'bg-red-950/40 border border-red-800/50 text-red-300'
              : 'bg-[#1e1e1e] border border-[#2e2e2e] text-gray-200',
          ].join(' ')}
        >
          {message.content.split('\n').map((line, i, arr) => (
            <span key={i}>
              {line}
              {i < arr.length - 1 && <br />}
            </span>
          ))}
          {message.streaming && (
            <span className="inline-block w-0.5 h-3.5 bg-gray-400 ml-0.5 align-middle animate-pulse" />
          )}
        </div>

        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-1">
            {message.toolCalls.map((tool, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 text-[10px] font-medium text-gray-500 bg-[#1a1a1a] border border-[#2e2e2e] rounded-full px-2 py-0.5"
              >
                <span className="w-1 h-1 rounded-full bg-[#e10600]" />
                {TOOL_LABELS[tool] ?? tool}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
