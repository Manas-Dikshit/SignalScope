export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className ?? "h-7 w-7"}
      role="img"
      aria-label="SignalScope"
    >
      <rect width="32" height="32" rx="7" fill="hsl(var(--primary))" fillOpacity="0.12" />
      <path
        d="M4 20c3-9 6-9 9 0s6 9 9 0 6-9 9 0"
        stroke="hsl(var(--primary))"
        strokeWidth="2.2"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="25" cy="14" r="2" fill="hsl(var(--secondary))" />
    </svg>
  );
}