export function Loading({ progress, error, subtle = false }: { progress: number; error: string | null; subtle?: boolean }) {
  return (
    <div
      className={`absolute inset-0 flex flex-col items-center justify-center ${subtle ? 'bg-black/60' : 'bg-black'}`}
      role="status"
      aria-live="polite"
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.34em] text-white/70">
        {error ? 'Could not load the circuit' : 'Loading the grid'}
      </p>
      <div className="mt-4 h-[2px] w-40 overflow-hidden bg-white/10">
        <div className="h-full bg-race transition-[width] duration-300" style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>
      {error && <p className="mt-4 max-w-xs text-center text-xs text-white/50">Check your connection and reload the page.</p>}
    </div>
  )
}
