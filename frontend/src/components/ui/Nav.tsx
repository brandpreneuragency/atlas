import { NavLink } from 'react-router-dom'

const items = [
  ['/', 'Mission Control'],
  ['/automation', 'Automation'],
  ['/files', 'Files'],
  ['/agent', 'Agent'],
  ['/models', 'Models'],
  ['/inbox', 'Inbox'],
  ['/settings', 'Settings'],
] as const

export function Nav() {
  return (
    <nav className="space-y-1">
      {items.map(([to, label]) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `block rounded-xl px-3 py-2 text-sm transition ${
              isActive
                ? 'bg-cyan-400/15 text-cyan-200'
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-100'
            }`
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  )
}
