import { Link } from "react-router-dom";
import { brand } from "../content/brand";

const markets = [
  {
    name: "Colombia",
    hub: `${brand.colombiaLocations} restaurants in Medellín, Bogotá and Cali`,
    accent: "border-brasa-leaf",
    copy: "Hours: Mon–Sun 11:00 AM – 10:00 PM. Headquarters in Medellín keeps the original grill standard.",
  },
  {
    name: "United States (Florida)",
    hub: `${brand.floridaLocations} restaurants in Miami and Orlando`,
    accent: "border-brasa-teal",
    copy: "Hours: Mon–Sun 11:00 AM – 10:00 PM. Miami office coordinates Florida locations — same recipes, second market.",
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
