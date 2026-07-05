export function Skeleton({ w = "100%", h = "1rem", rounded = "0.5rem", className = "" }) {
  return <div className={`shimmer ${className}`} style={{ width: w, height: h, borderRadius: rounded }} />;
}

export function SkeletonText({ lines = 3, className = "" }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} h="0.75rem" w={i === lines - 1 ? "60%" : "100%"} />
      ))}
    </div>
  );
}

export function SkeletonRows({ rows = 5, cols = 4, className = "" }) {
  return (
    <div className={`space-y-2.5 ${className}`}>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} h="0.85rem" w={c === 0 ? "3.5rem" : "100%"} className="flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart({ height = 256, className = "" }) {
  return <Skeleton h={`${height}px`} w="100%" rounded="0.75rem" className={className} />;
}

export function SkeletonMetric({ className = "" }) {
  return (
    <div className={`space-y-2 ${className}`}>
      <Skeleton h="0.7rem" w="40%" />
      <Skeleton h="1.6rem" w="70%" />
    </div>
  );
}
