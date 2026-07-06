import ReactMarkdown from 'react-markdown'

export function Preview({
  path,
  content,
  onEdit,
}: {
  path: string
  content: string
  onEdit: () => void
}) {
  const isMarkdown = path.toLowerCase().endsWith('.md')
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-slate-500">{path}</span>
        <button
          type="button"
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          onClick={onEdit}
        >
          Edit
        </button>
      </div>
      {isMarkdown ? (
        <article className="prose prose-invert max-w-none rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
          <ReactMarkdown>{content}</ReactMarkdown>
        </article>
      ) : (
        <pre className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950 p-5 text-sm text-slate-200">
          {content}
        </pre>
      )}
    </div>
  )
}
