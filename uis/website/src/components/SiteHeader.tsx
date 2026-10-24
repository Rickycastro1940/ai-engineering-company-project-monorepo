import { Link, NavLink } from "react-router-dom";
import { brand } from "../content/brand";
import { useI18n, type Lang } from "../i18n/LanguageContext";

export function SiteHeader() {
  const { t, lang, setLang } = useI18n();
  const links = [
    { to: "/", label: t.nav.home, end: true },
    { to: "/locations", label: t.nav.locations },
    { to: "/#story", label: t.nav.menu },
    { to: "/brasa-points", label: t.nav.points },
    { to: "/#contact", label: t.nav.contact },
  ];

  return (
    <header className="sticky top-0 z-20 min-h-[4.25rem] border-b border-brasa-charcoal/10 bg-brasa-paper/90 backdrop-blur-[10px]">
      <div className="mx-auto flex min-h-[4.25rem] w-[min(100%-1rem,68rem)] items-center gap-2 md:w-[min(100%-2rem,68rem)] md:gap-6">
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
        <nav className="hidden gap-4 text-[0.92rem] font-semibold lg:flex" aria-label="Primary">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `no-underline transition-colors ${
                  isActive && link.to !== "/#story" && link.to !== "/#contact"
                    ? "text-brasa-charcoal"
                    : "text-brasa-muted hover:text-brasa-charcoal"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center rounded-[0.35rem] border border-brasa-charcoal/15 p-0.5" role="group" aria-label={t.langLabel}>
          {(["en", "es"] as const satisfies readonly Lang[]).map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => setLang(code)}
              aria-pressed={lang === code}
              className={`min-h-9 min-w-10 rounded-[0.25rem] px-2 font-display text-xs font-bold tracking-wide ${
                lang === code ? "bg-brasa-charcoal text-white" : "text-brasa-muted hover:text-brasa-charcoal"
              }`}
            >
              {code.toUpperCase()}
            </button>
          ))}
        </div>
        <Link
          to="/join"
          className="inline-flex max-w-[8.5rem] items-center justify-center whitespace-normal rounded-[0.35rem] bg-brasa-ember px-2.5 py-2 text-center font-display text-xs font-semibold leading-tight text-white no-underline transition-colors hover:bg-brasa-ember-deep focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember sm:max-w-none sm:whitespace-nowrap sm:px-4 sm:text-sm"
        >
          {t.nav.join}
        </Link>
      </div>
    </header>
  );
}
