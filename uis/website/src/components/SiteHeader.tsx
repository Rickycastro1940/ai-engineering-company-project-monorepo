import { Link, NavLink } from "react-router-dom";
import { brand } from "../content/brand";

const links = [
  { to: "/#commitments", label: "Our promise" },
  { to: "/locations", label: "Locations" },
  { to: "/brasa-points", label: "Brasa Points" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-20 h-[4.25rem] border-b border-brasa-charcoal/10 bg-brasa-paper/90 backdrop-blur-[10px]">
      <div className="mx-auto flex h-full w-[min(100%-2rem,68rem)] items-center gap-6">
        <Link
          to="/"
          className="mr-auto inline-flex items-center gap-2.5 no-underline"
          aria-label={`${brand.name} home`}
        >
          <span
            className="size-[1.15rem] rounded-full bg-[radial-gradient(circle_at_35%_35%,#ffb703,var(--color-brasa-ember)_55%,var(--color-brasa-charcoal))] shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-brasa-ember)_25%,transparent)]"
            aria-hidden="true"
          />
          <span className="font-display text-xl font-bold tracking-tight">{brand.name}</span>
        </Link>
        <nav className="hidden gap-5 text-[0.95rem] font-semibold md:flex" aria-label="Primary">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `no-underline transition-colors ${
                  isActive ? "text-brasa-charcoal" : "text-brasa-muted hover:text-brasa-charcoal"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <Link
          to="/locations"
          className="inline-flex items-center justify-center rounded-[0.35rem] bg-brasa-ember px-4 py-2 font-display text-sm font-semibold text-white no-underline transition-colors hover:bg-brasa-ember-deep focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember"
        >
          Find a location
        </Link>
      </div>
    </header>
  );
}
