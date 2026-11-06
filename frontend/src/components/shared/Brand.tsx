import { Sparkles } from 'lucide-react'

interface BrandProps {
  size?: 'small' | 'large'
  showName?: boolean
  nameClassName?: string
  className?: string
}

export default function Brand({
  size = 'small',
  showName = true,
  nameClassName = '',
  className = '',
}: BrandProps) {
  const large = size === 'large'

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div className={`flex shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-cyan-400 text-slate-950 shadow-lg shadow-indigo-500/30 ${large ? 'h-11 w-11' : 'h-9 w-9'}`}>
        <Sparkles size={large ? 20 : 18} aria-hidden="true" />
      </div>
      {showName && (
        <div className={`leading-tight ${nameClassName}`}>
          <div className={`font-semibold uppercase tracking-[0.25em] text-indigo-300 ${large ? 'text-xs' : 'text-[10px]'}`}>Apex</div>
          <div className={`font-semibold text-slate-50 ${large ? 'text-lg' : 'text-sm'}`}>Recruit</div>
        </div>
      )}
    </div>
  )
}
