import { brand } from "../content/brand";

export function BrandPillars() {
  return (
    <section
      id="commitments"
      className="bg-brasa-paper py-16 md:py-20"
      aria-labelledby="pillars-title"
    >
      <div className="mx-auto w-[min(100%-2rem,68rem)]">
        <p className="mb-4 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-teal">
          What we stand for
        </p>
        <h2 id="pillars-title" className="mb-4 text-[clamp(1.75rem,3vw,2.35rem)]">
          Three commitments in every kitchen
        </h2>
        <p className="max-w-xl text-lg text-brasa-muted">
          From a single family grill in Medellín to {brand.locations} company-owned
          restaurants, Brasaland still runs on the same three promises.
        </p>
        <ul className="mt-10 grid list-none gap-6 p-0 md:grid-cols-3">
          {brand.commitments.map((item, index) => (
            <li
              key={item.title}
              className="border-t-[3px] border-brasa-ember pt-6 animate-fade-up"
              style={{ animationDelay: `${index * 120}ms` }}
            >
              <h3 className="mb-2 text-xl">{item.title}</h3>
              <p className="text-brasa-muted">{item.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
