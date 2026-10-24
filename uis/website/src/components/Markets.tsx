import { Link } from "react-router-dom";
import { useI18n } from "../i18n/LanguageContext";

export function Markets() {
  const { t } = useI18n();
  const markets = [
    {
      name: t.markets.colombiaName,
      hub: t.markets.colombiaHub,
      accent: "border-brasa-leaf",
      copy: t.markets.colombiaCopy,
    },
    {
      name: t.markets.floridaName,
      hub: t.markets.floridaHub,
      accent: "border-brasa-teal",
      copy: t.markets.floridaCopy,
    },
  ];

  return (
    <section id="markets" className="bg-brasa-stone py-16 md:py-20" aria-labelledby="markets-title">
      <div className="mx-auto w-[min(100%-2rem,68rem)]">
        <p className="mb-4 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-teal">
          {t.markets.eyebrow}
        </p>
        <h2 id="markets-title" className="mb-4 text-[clamp(1.75rem,3vw,2.35rem)]">
          {t.markets.title}
        </h2>
        <p className="max-w-xl text-lg text-brasa-muted">{t.markets.lead}</p>
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
            {t.markets.roster}
          </Link>
        </p>
      </div>
    </section>
  );
}
