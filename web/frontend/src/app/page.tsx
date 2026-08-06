import Link from "next/link";
import { Brand } from "@/components/brand";

export default function HomePage() {
  return (
    <main className="landing">
      <header><Brand /><Link className="button ghost" href="/login">Enter film room</Link></header>
      <div className="landing-grid">
        <section>
          <p className="eyebrow">AI TENNIS HIGHLIGHT EDITOR</p>
          <h1>The match.<br /><em>Only the pulse.</em></h1>
          <p className="landing-copy">
            Upload a full match. Breakpoint finds every rally, scores the energy,
            and hands you a precise editorial desk for the final cut.
          </p>
          <Link className="button primary" href="/register">Start a match →</Link>
        </section>
        <aside className="court-poster" aria-label="Stylized tennis court">
          <div className="poster-number">BP<br />01</div>
          <div className="court-lines"><i /><i /><i /></div>
          <p>FULL MATCH<br />TO FINAL CUT</p>
        </aside>
      </div>
    </main>
  );
}
