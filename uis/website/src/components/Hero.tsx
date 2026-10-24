import { Link } from "react-router-dom";
import { useI18n } from "../i18n/LanguageContext";

export function Hero() {
  const { t } = useI18n();

  return (
    <section
      className="relative grid min-h-[calc(100svh-4.25rem)] items-end overflow-hidden bg-brasa-charcoal text-white"
      aria-labelledby="hero-headline"
    >
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="hero-glow absolute inset-x-[-10%] bottom-[-35%] h-[70%] animate-ember-pulse" />
        <div className="hero-grill absolute inset-0" />
      </div>
      <div className="relative z-10 mx-auto w-[min(100%-2rem,68rem)] max-w-2xl py-16 pb-12 animate-fade-up">
        <p className="mb-3 font-display text-[0.85rem] font-semibold uppercase tracking-[0.1em] text-white/75">
          {t.hero.kicker}
        </p>
        <h1
          id="hero-headline"
          className="mb-5 font-display text-[clamp(2.4rem,8vw,4.5rem)] leading-[1.02] tracking-[-0.03em]"
        >
          {t.hero.headline}
        </h1>
        <p className="mb-8 max-w-xl text-[clamp(1.05rem,2.2vw,1.3rem)] text-white/90">{t.hero.sub}</p>
        <div className="flex flex-wrap gap-4">
          <Link
            to="/join"
            className="inline-flex items-center justify-center rounded-[0.35rem] bg-brasa-ember px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline transition-colors hover:bg-brasa-ember-deep focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember"
          >
            {t.nav.join}
          </Link>
          <Link
            to="/locations"
            className="inline-flex items-center justify-center rounded-[0.35rem] border-2 border-white/55 bg-transparent px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline transition-colors hover:bg-white/10 focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember"
          >
            {t.hero.locations}
          </Link>
        </div>
      </div>
    </section>
  );
}
