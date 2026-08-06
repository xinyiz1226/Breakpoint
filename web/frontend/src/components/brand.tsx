import Link from "next/link";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className={`brand ${compact ? "brand-compact" : ""}`}>
      <span className="brand-mark" aria-hidden="true">
        <i />
        <i />
      </span>
      <span>BREAKPOINT</span>
    </Link>
  );
}
