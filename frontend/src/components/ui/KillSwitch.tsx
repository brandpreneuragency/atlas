import { useEffect, useState } from 'react'

import { api } from '../../api/client'
import { ConfirmDialog } from '../files/ConfirmDialog'

export function KillSwitch() {
  const [paused, setPaused] = useState<boolean | null>(null)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    api
      .get<{ paused: boolean }>('/api/killswitch')
      .then((body) => setPaused(body.paused))
      .catch(() => setPaused(null))
  }, [])

  const flip = async () => {
    const target = !(paused ?? false)
    try {
      await api.post('/api/killswitch', { paused: target })
      setPaused(target)
    } finally {
      setConfirming(false)
    }
  }

  return (
    <>
      <button
        type="button"
        aria-label="kill switch"
        className={`rounded-lg px-3 py-1 text-sm font-medium ${
          paused
            ? 'bg-red-500 text-white'
            : 'border border-slate-700 text-slate-300 hover:bg-slate-800'
        }`}
        onClick={() => setConfirming(true)}
      >
        {paused ? 'Kill switch: ENGAGED' : 'Kill switch'}
      </button>
      {confirming && (
        <ConfirmDialog
          title={
            paused
              ? 'Release the kill switch? Paused Hermes jobs will resume.'
              : 'Engage the kill switch? All enabled Hermes jobs will be paused.'
          }
          paths={[]}
          confirmLabel={paused ? 'Release' : 'Engage'}
          onConfirm={() => void flip()}
          onCancel={() => setConfirming(false)}
        />
      )}
    </>
  )
}
