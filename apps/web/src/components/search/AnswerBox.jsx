export default function AnswerBox({ answer, queryType }) {
  if (!answer) return null

  return (
    <div className="card p-5 border-l-4 border-blue-500 bg-blue-50">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-blue-600 text-lg">✨</span>
        <span className="text-sm font-semibold text-blue-800">
          Grounded Answer
          <span className="ml-2 px-2 py-0.5 bg-blue-100 text-blue-600 rounded-full text-xs font-medium">
            {queryType}
          </span>
        </span>
      </div>
      <p className="text-gray-800 text-sm leading-relaxed whitespace-pre-wrap">{answer}</p>
    </div>
  )
}
