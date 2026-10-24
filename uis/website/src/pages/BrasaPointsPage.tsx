import { Link } from "react-router-dom";
import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";
import { brand } from "../content/brand";
import { ORDERING_NOTE } from "../content/loyaltySignup";

const steps = [
  {
    title: "Earn on every visit",
    body: "Accumulate 1 point for every $10,000 COP or $5 USD spent at any Brasaland location.",
  },
  {
    title: "Redeem rewards",
    body: "Use points for discounts and free dishes. Members also get exclusive offers.",
  },
  {
    title: "Register once, digital",
    body: "Sign up online — no more lost paper stamp cards. Guests must be 18 or older.",
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
            <p className="mt-8">
              <Link
                to="/join"
                className="inline-flex rounded-[0.35rem] bg-brasa-ember px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline hover:bg-brasa-ember-deep"
              >
                Join Brasa Points
              </Link>
            </p>
          </div>
        </section>

        <section className="bg-brasa-paper py-14 md:py-16" aria-labelledby="points-how">
          <div className="mx-auto w-[min(100%-2rem,68rem)]">
            <h2 id="points-how" className="mb-8 text-[clamp(1.75rem,3vw,2.35rem)]">
              Earn points with every visit
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
            <p className="mt-8 max-w-2xl rounded-[0.35rem] border border-brasa-charcoal/10 bg-brasa-stone px-4 py-3 text-brasa-muted" role="note">
              {ORDERING_NOTE}
            </p>
            <p className="mt-10 flex flex-wrap gap-4">
              <Link
                to="/join"
                className="font-display font-semibold text-brasa-ember no-underline hover:text-brasa-ember-deep"
              >
                Open the registration form →
              </Link>
              <Link
                to="/locations"
                className="font-display font-semibold text-brasa-charcoal no-underline hover:text-brasa-ember"
              >
                Browse locations →
              </Link>
            </p>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
