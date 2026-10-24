import { Link } from "react-router-dom";
import { useI18n } from "../i18n/LanguageContext";

export function LoyaltyTeaser() {
  const { t } = useI18n();

  return (
    <section
      id="brasa-points"
      className="bg-brasa-charcoal py-16 text-white md:py-20"
      aria-labelledby="loyalty-title"
    >
      <div className="mx-auto grid w-[min(100%-2rem,68rem)] items-start gap-10 md:grid-cols-[1.3fr_0.9fr]">
        <div className="animate-fade-in">
          <p className="mb-4 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-ember">
            {t.loyalty.eyebrow}
          </p>
          <h2 id="loyalty-title" className="mb-4 text-[clamp(1.75rem,3vw,2.35rem)]">
            {t.loyalty.title}
          </h2>
          <p className="max-w-xl text-lg text-white/80">{t.loyalty.lead}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to="/join"
              className="inline-flex items-center justify-center rounded-[0.35rem] bg-brasa-ember px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline transition-colors hover:bg-brasa-ember-deep focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember"
            >
              {t.nav.join}
            </Link>
            <Link
              to="/brasa-points"
              className="inline-flex items-center justify-center rounded-[0.35rem] border border-white/40 px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline hover:bg-white/10"
            >
              {t.loyalty.how}
            </Link>
          </div>
        </div>
        <aside className="border border-white/20 bg-white/5 p-6" aria-label={t.loyalty.aside}>
          <p className="mb-1 font-display text-xs uppercase tracking-[0.08em] text-white/60">
            {t.loyalty.aside}
          </p>
          <p className="mb-4 font-display text-[1.75rem] font-bold">{t.loyalty.title}</p>
          <ul className="list-disc space-y-2 pl-5 text-white/80">
            {t.loyalty.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        </aside>
      </div>
    </section>
  );
}
