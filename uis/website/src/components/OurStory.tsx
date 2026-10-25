import { useI18n } from "../i18n/LanguageContext";

export function OurStory() {
  const { t } = useI18n();

  return (
    <section id="story" className="bg-brasa-paper py-16 md:py-20" aria-labelledby="story-title">
      <div className="mx-auto grid w-[min(100%-2rem,68rem)] items-center gap-10 md:grid-cols-2">
        <div>
          <p className="mb-4 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-ember">
            {t.story.eyebrow}
          </p>
          <h2 id="story-title" className="mb-4 text-[clamp(1.75rem,3vw,2.35rem)]">
            {t.story.title}
          </h2>
          <p className="text-lg leading-relaxed text-brasa-muted">{t.story.body}</p>
        </div>
        <figure className="overflow-hidden rounded-[0.5rem] bg-brasa-charcoal">
          <svg
            viewBox="0 0 640 480"
            role="img"
            aria-label={t.story.alt}
            className="aspect-[4/3] w-full"
          >
            <rect width="640" height="480" fill="#1c1917" />
            <ellipse cx="320" cy="390" rx="220" ry="28" fill="#e85d04" opacity="0.35" />
            <path d="M120 250h400v18H120z" fill="#57534e" />
            {Array.from({ length: 9 }, (_, index) => (
              <rect key={index} x={150 + index * 40} y="210" width="8" height="58" rx="2" fill="#e8e6e1" />
            ))}
            <path d="M180 188c20-48 70-48 90 0" fill="none" stroke="#ffb703" strokeWidth="10" strokeLinecap="round" />
            <path d="M300 176c18-40 64-40 82 0" fill="none" stroke="#e85d04" strokeWidth="10" strokeLinecap="round" />
            <path d="M410 190c16-36 52-36 68 0" fill="none" stroke="#ffb703" strokeWidth="8" strokeLinecap="round" />
          </svg>
          <figcaption className="px-4 py-3 font-display text-sm text-white/75">{t.story.caption}</figcaption>
        </figure>
      </div>
    </section>
  );
}
