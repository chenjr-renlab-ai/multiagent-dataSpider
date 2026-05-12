import { clsx } from 'clsx'
import type { ReactNode } from 'react'

type BadgeVariant = 'green' | 'red' | 'yellow' | 'blue' | 'gray' | 'orange'

interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  className?: string
}

const variantClasses: Record<BadgeVariant, string> = {
  green: 'bg-green-900 text-green-300 border-green-700',
  red: 'bg-red-900 text-red-300 border-red-700',
  yellow: 'bg-yellow-900 text-yellow-300 border-yellow-700',
  blue: 'bg-blue-900 text-blue-300 border-blue-700',
  gray: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  orange: 'bg-orange-900 text-orange-300 border-orange-700',
}

export function Badge({ variant = 'gray', children, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium border',
        variantClasses[variant],
        className
      )}
    >
      {children}
    </span>
  )
}
