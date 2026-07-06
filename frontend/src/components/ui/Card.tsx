import type { ReactNode } from 'react'

type CardProps = {
  title: string
  children: ReactNode
}

export function Card({ title, children }: CardProps) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl shadow-black/20">
      <h2 className="mb-3 text-lg font-semibold text-slate-100">{title}</h2>
      {children}
    </section>
  )
}
