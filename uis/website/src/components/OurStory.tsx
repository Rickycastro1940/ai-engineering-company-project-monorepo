import { brand } from "../content/brand";

export function OurStory() {
  return (
    <section id="story" className="bg-brasa-paper py-16 md:py-20" aria-labelledby="story-title">
      <div className="mx-auto grid w-[min(100%-2rem,68rem)] items-center gap-10 md:grid-cols-2">
        <div>
          <p className="mb-4 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-ember">
            Our story
          </p>
          <h2 id="story-title" className="mb-4 text-[clamp(1.75rem,3vw,2.35rem)]">
            From one Medellín kitchen to two countries
          </h2>
          <p className="text-lg leading-relaxed text-brasa-muted">{brand.story}</p>
        </div>
        <figure className="overflow-hidden rounded-[0.5rem] bg-brasa-charcoal">
          <img
            src="https://images.unsplash.com/photo-1555939594-58edc71eb336?auto=format&fit=crop&w=1200&q=80"
            alt="Grilled meat on an open charcoal grill at a Brasaland-style kitchen"
            className="aspect-[4/3] w-full object-cover opacity-95"
            width={1200}
            height={900}
          />
          <figcaption className="px-4 py-3 font-display text-sm text-white/75">
            Fresh product, traditional techniques, and a kitchen that moves fast.
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
