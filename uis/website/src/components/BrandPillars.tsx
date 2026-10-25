import { useI18n } from "../i18n/LanguageContext";

export function BrandPillars() {
  const { t } = useI18n();

  return (
    <section
      id="commitments"
      className="bg-brasa-paper py-16 md:py-20"
      aria-labelledby="pillars-title"
    >
      <div className="mx-auto w-[min(100%-2rem,68rem)]">
        <p className="mb-4 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-teal">
          {t.pillars.eyebrow}
        </p>
        <h2 id="pillars-title" className="mb-4 text-[clamp(1.75rem,3vw,2.35rem)]">
          {t.pillars.title}
        </h2>
        <p className="max-w-xl text-lg text-brasa-muted">{t.pillars.lead}</p>
        <ul className="mt-10 grid list-none gap-6 p-0 md:grid-cols-3">
          {t.pillars.items.map((item, index) => (
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
