import { Link } from "react-router-dom";
import { brand } from "../content/brand";

export function Hero() {
  return (
    <section
      className="relative grid min-h-[calc(100svh-4.25rem)] items-end overflow-hidden bg-brasa-charcoal text-white"
      aria-labelledby="hero-brand"
    >
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="hero-glow absolute inset-x-[-10%] bottom-[-35%] h-[70%] animate-ember-pulse" />
        <div className="hero-grill absolute inset-0" />
      </div>
      <div className="relative z-10 mx-auto w-[min(100%-2rem,68rem)] max-w-xl py-16 pb-12 animate-fade-up">
        <p className="mb-4 font-display text-[0.85rem] font-semibold uppercase tracking-[0.1em] text-white/75">
          Since {brand.founded} · {brand.markets.join(" + ")}
        </p>
        <h1
          id="hero-brand"
          className="mb-6 font-display text-[clamp(3.2rem,12vw,6.5rem)] leading-[0.95] tracking-[-0.04em]"
        >
          {brand.name}
        </h1>
        <p className="mb-8 max-w-md text-[clamp(1.15rem,2.4vw,1.45rem)] text-white/90">
          {brand.tagline}
        </p>
        <div className="flex flex-wrap gap-4">
          <Link
            to="/locations"
            className="inline-flex items-center justify-center rounded-[0.35rem] bg-brasa-ember px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline transition-colors hover:bg-brasa-ember-deep focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember"
          >
            Explore {brand.locations} locations
          </Link>
          <Link
            to="/brasa-points"
            className="inline-flex items-center justify-center rounded-[0.35rem] border-2 border-white/55 bg-transparent px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline transition-colors hover:bg-white/10 focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember"
          >
            Learn about {brand.loyalty.name}
          </Link>
        </div>
      </div>
    </section>
  );
}
