const SUGGESTIONS = [
  "Who has the most F1 World Championships?",
  "Who is Lewis Hamilton's teammate?",
  "When did Lando Norris get his first win?",
  "How many races has Kimi Antonelli won?",
];

interface WelcomeScreenProps {
  onSuggestion: (text: string) => void;
}

export default function WelcomeScreen({ onSuggestion }: WelcomeScreenProps) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 px-6 py-12 text-center">
      <div className="mb-8">
        <div className="flex items-center justify-center gap-2 mb-4">
          <div className="w-1.5 h-10 bg-[#e10600] rounded-sm" />
          <span className="text-white font-bold text-4xl tracking-tight">F1</span>
          <div className="w-1.5 h-10 bg-[#e10600] rounded-sm" />
        </div>
        <h1 className="text-2xl font-semibold text-white mb-2">
          Formula 1 AI Chatbot
        </h1>
        <p className="text-gray-500 text-sm max-w-md">
          Ask me anything about Formula 1.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-xl">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onSuggestion(s)}
            className="text-left px-4 py-3 bg-[#1e1e1e] border border-[#2e2e2e] rounded-xl text-sm text-gray-400 hover:text-gray-200 hover:border-[#444] hover:bg-[#242424] transition-all cursor-pointer"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
