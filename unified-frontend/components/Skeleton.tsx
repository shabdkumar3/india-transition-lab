/**
 * Loading skeleton components — used while API calls are in flight.
 */

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-muted/60 ${className}`}
      aria-hidden="true"
    />
  );
}

export function KpiSkeleton() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="border border-border rounded-xl bg-card px-4 py-4">
          <Skeleton className="h-3 w-24 mb-3" />
          <Skeleton className="h-7 w-20" />
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 300 }: { height?: number }) {
  return (
    <div
      className="border border-border rounded-xl bg-card p-5 mb-6 flex items-center justify-center"
      style={{ height: height + 56 }}
    >
      <div className="text-center">
        <div className="flex gap-1 justify-center mb-3">
          {[40, 65, 50, 80, 60, 75, 55, 90].map((h, i) => (
            <div
              key={i}
              className="w-5 rounded-t bg-muted/60 animate-pulse"
              style={{ height: h * 0.6, animationDelay: `${i * 80}ms` }}
            />
          ))}
        </div>
        <p className="text-xs text-muted-foreground">Computing…</p>
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="border border-border rounded-xl bg-card overflow-hidden mb-8">
      <div className="px-5 py-4 border-b border-border">
        <Skeleton className="h-4 w-48" />
      </div>
      <div className="divide-y divide-border/50">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-4 px-5 py-3">
            {Array.from({ length: cols }).map((_, c) => (
              <Skeleton key={c} className={`h-3 ${c === 0 ? "w-32" : "w-16 ml-auto"}`} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
