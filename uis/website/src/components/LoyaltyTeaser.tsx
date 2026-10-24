import { Link } from "react-router-dom";
import { brand } from "../content/brand";

export function LoyaltyTeaser() {
  return (
    <section
      id="brasa-points"
      className="bg-brasa-charcoal py-16 text-white md:py-20"
      aria-labelledby="loyalty-title"
    >
      <div className="mx-auto grid w-[min(100%-2rem,68rem)] items-start gap-10 md:grid-cols-[1.3fr_0.9fr]">
        <div className="animate-fade-in">
          <p className="mb-4 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-ember">
            Loyalty
          </p>
          <h2 id="loyalty-title" className="mb-4 text-[clamp(1.75rem,3vw,2.35rem)]">
            {brand.loyalty.name}
          </h2>
          <p className="max-w-xl text-lg text-white/80">{brand.loyalty.status}</p>
          <p className="mt-6">
            <Link
              to="/brasa-points"
              className="inline-flex items-center justify-center rounded-[0.35rem] bg-brasa-ember px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline transition-colors hover:bg-brasa-ember-deep focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember"
            >
              How Brasa Points works today
            </Link>
          </p>
        </div>
        <aside
          className="border border-white/20 bg-white/5 p-6"
          aria-label="Programme status"
        >
          <p className="mb-1 font-display text-xs uppercase tracking-[0.08em] text-white/60">
            Guest programme
          </p>
          <p className="mb-4 font-display text-[1.75rem] font-bold">{brand.loyalty.name}</p>
          <p className="text-white/80">
            Physical stamp cards still define today’s experience. Digital ordering
            and a customer CRM are on the Brasaland Digital roadmap for Marketing.
          </p>
        </aside>
      </div>
    </section>
  );
}
