import { useSession } from '../../stores/useSession'

/** Banner shown while the live event stream is disconnected. */
export function ConnectionBanner() {
  const status = useSession((s) => s.sseStatus)
  if (status !== 'closed') return null
  return (
    <div className="border-b border-amber-500/30 bg-amber-500/10 px-8 py-2 text-center text-sm text-amber-300">
      Live feed disconnected — reconnecting…
    </div>
  )
}
