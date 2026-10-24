import { Link } from "react-router-dom";
import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";
import { brand } from "../content/brand";

const steps = [
  {
    title: "Earn on visits",
    body: "Guests collect stamps on a physical card — about 60% of customers still do not use the programme today.",
  },
  {
    title: "Redeem in-restaurant",
    body: "Rewards stay tied to the card you carry. There is no digital wallet or app balance yet.",
  },
  {
    title: "What Brasaland Digital is building",
    body: "Camila Ospina’s Marketing team needs a digital loyalty experience, customer CRM, and personalisation — still on the roadmap.",
  },
];

export function BrasaPointsPage() {
  return (
    <>
      <SiteHeader />
      <main id="main-content">
        <section className="bg-brasa-charcoal px-4 py-16 text-white md:py-20">
          <div className="mx-auto w-[min(100%,68rem)] animate-fade-up">
            <p className="mb-3 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-ember">
              Loyalty programme
            </p>
            <h1 className="mb-4 text-[clamp(2.25rem,6vw,3.5rem)] tracking-tight">
              {brand.loyalty.name}
            </h1>
            <p className="max-w-2xl text-lg text-white/85">{brand.loyalty.status}</p>
          </div>
        </section>

        <section className="bg-brasa-paper py-14 md:py-16" aria-labelledby="points-how">
          <div className="mx-auto w-[min(100%-2rem,68rem)]">
            <h2 id="points-how" className="mb-8 text-[clamp(1.75rem,3vw,2.35rem)]">
              How it works today
            </h2>
            <ol className="grid list-none gap-8 p-0 md:grid-cols-3">
              {steps.map((step, index) => (
                <li
                  key={step.title}
                  className="border-t-[3px] border-brasa-ember pt-5 animate-fade-up"
                  style={{ animationDelay: `${index * 100}ms` }}
                >
                  <p className="mb-2 font-display text-sm font-semibold text-brasa-teal">
                    Step {index + 1}
                  </p>
                  <h3 className="mb-2 text-xl">{step.title}</h3>
                  <p className="text-brasa-muted">{step.body}</p>
                </li>
              ))}
            </ol>
            <p className="mt-10">
              <Link
                to="/locations"
                className="inline-flex items-center justify-center rounded-[0.35rem] bg-brasa-ember px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline transition-colors hover:bg-brasa-ember-deep focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember"
              >
                Visit a Brasaland location
              </Link>
            </p>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
