import { Link } from "react-router-dom";
import { brand } from "../content/brand";

const markets = [
  {
    name: "Colombia",
    hub: brand.hq,
    accent: "border-brasa-leaf",
    copy: "Headquarters and the roots of the brand. Company-owned kitchens across the country keep the original Medellín standard.",
  },
  {
    name: "Florida, United States",
    hub: brand.miamiOffice,
    accent: "border-brasa-teal",
    copy: "Commercial and operations office in Miami coordinates Florida locations — same grill standards, second market.",
  },
];

export function Markets() {
  return (
    <section
      id="markets"
      className="bg-brasa-stone py-16 md:py-20"
      aria-labelledby="markets-title"
    >
      <div className="mx-auto w-[min(100%-2rem,68rem)]">
        <p className="mb-4 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-teal">
          Two countries · {brand.currencies.join(" & ")}
        </p>
        <h2 id="markets-title" className="mb-4 text-[clamp(1.75rem,3vw,2.35rem)]">
          {brand.locations} locations. One standard.
        </h2>
        <p className="max-w-xl text-lg text-brasa-muted">
          About {brand.employees} people run Brasaland across Colombia and Florida —
          one chain, two labour markets, one plate that should taste the same.
        </p>
        <div className="mt-10 grid gap-6 md:grid-cols-2">
          {markets.map((market) => (
            <article
              key={market.name}
              className={`border-l-4 bg-brasa-paper py-6 pl-6 pr-4 ${market.accent}`}
            >
              <h3 className="mb-1 text-[1.4rem]">{market.name}</h3>
              <p className="mb-4 font-display font-semibold text-brasa-muted">{market.hub}</p>
              <p className="text-brasa-ink/90">{market.copy}</p>
            </article>
          ))}
        </div>
        <p className="mt-8">
          <Link
            to="/locations"
            className="font-display font-semibold text-brasa-ember no-underline hover:text-brasa-ember-deep"
          >
            See the full location roster →
          </Link>
        </p>
      </div>
    </section>
  );
}
