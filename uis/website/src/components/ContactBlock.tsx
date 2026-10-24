import { Link } from "react-router-dom";
import { brand } from "../content/brand";
import { ORDERING_NOTE } from "../content/loyaltySignup";

export function ContactBlock() {
  return (
    <section id="contact" className="bg-brasa-stone py-16 md:py-20" aria-labelledby="contact-title">
      <div className="mx-auto w-[min(100%-2rem,68rem)]">
        <p className="mb-4 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-teal">
          Contact
        </p>
        <h2 id="contact-title" className="mb-6 text-[clamp(1.75rem,3vw,2.35rem)]">
          Talk to Brasaland
        </h2>
        <ul className="mb-8 grid gap-3 text-lg text-brasa-ink md:grid-cols-3">
          <li>
            <span className="block font-display text-sm font-semibold uppercase tracking-wide text-brasa-muted">
              Email
            </span>
            <a className="font-semibold text-brasa-ember no-underline hover:text-brasa-ember-deep" href={`mailto:${brand.contact.email}`}>
              {brand.contact.email}
            </a>
          </li>
          <li>
            <span className="block font-display text-sm font-semibold uppercase tracking-wide text-brasa-muted">
              Colombia
            </span>
            <a className="font-semibold no-underline" href={`tel:${brand.contact.colombiaPhone.replace(/\s/g, "")}`}>
              {brand.contact.colombiaPhone}
            </a>
          </li>
          <li>
            <span className="block font-display text-sm font-semibold uppercase tracking-wide text-brasa-muted">
              Florida
            </span>
            <a className="font-semibold no-underline" href={`tel:${brand.contact.floridaPhone.replace(/\s/g, "")}`}>
              {brand.contact.floridaPhone}
            </a>
          </li>
        </ul>
        <p className="mb-6 max-w-2xl rounded-[0.35rem] border border-brasa-charcoal/10 bg-brasa-paper px-4 py-3 text-brasa-muted" role="note">
          {ORDERING_NOTE}
        </p>
        <Link
          to="/join"
          className="inline-flex rounded-[0.35rem] bg-brasa-ember px-5 py-3.5 font-display text-[0.95rem] font-semibold text-white no-underline hover:bg-brasa-ember-deep"
        >
          Join Brasa Points
        </Link>
      </div>
    </section>
  );
}
