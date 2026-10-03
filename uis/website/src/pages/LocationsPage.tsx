import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";
import { brand } from "../content/brand";
import { locations } from "../content/locations";

export function LocationsPage() {
  const colombia = locations.filter((row) => row.region === "Colombia");
  const florida = locations.filter((row) => row.region === "Florida");

  return (
    <>
      <SiteHeader />
      <main id="main-content">
        <section className="relative overflow-hidden bg-brasa-charcoal px-4 py-16 text-white md:py-20">
          <div className="hero-glow pointer-events-none absolute inset-x-[-10%] bottom-[-40%] h-[70%] animate-ember-pulse" aria-hidden="true" />
          <div className="relative z-10 mx-auto w-[min(100%,68rem)] animate-fade-up">
            <p className="mb-3 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-ember">
              {brand.markets.join(" · ")}
            </p>
            <h1 className="mb-4 text-[clamp(2.25rem,6vw,3.5rem)] tracking-tight">
              {brand.locations} company-owned locations
            </h1>
            <p className="max-w-2xl text-lg text-white/85">
              Same recipes in every kitchen. Menus list prices in COP and USD depending
              on the market — Colombia kitchens settle in COP; Florida kitchens in USD.
            </p>
          </div>
        </section>

        <section className="bg-brasa-paper py-14 md:py-16" aria-labelledby="colombia-roster">
          <div className="mx-auto w-[min(100%-2rem,68rem)]">
            <h2 id="colombia-roster" className="mb-2 text-2xl md:text-3xl">
              Colombia · COP
            </h2>
            <p className="mb-8 text-brasa-muted">HQ {brand.hq} · {colombia.length} restaurants</p>
            <ul className="grid list-none gap-3 p-0 sm:grid-cols-2 lg:grid-cols-4">
              {colombia.map((row) => (
                <li key={row.id} className="border-t-2 border-brasa-leaf pt-3">
                  <p className="font-display font-semibold text-brasa-ink">{row.name}</p>
                  <p className="text-sm text-brasa-muted">{row.city}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="bg-brasa-stone py-14 md:py-16" aria-labelledby="florida-roster">
          <div className="mx-auto w-[min(100%-2rem,68rem)]">
            <h2 id="florida-roster" className="mb-2 text-2xl md:text-3xl">
              Florida · USD
            </h2>
            <p className="mb-8 text-brasa-muted">
              Office {brand.miamiOffice} · {florida.length} restaurants
            </p>
            <ul className="grid list-none gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3">
              {florida.map((row) => (
                <li key={row.id} className="border-t-2 border-brasa-teal pt-3">
                  <p className="font-display font-semibold text-brasa-ink">{row.name}</p>
                  <p className="text-sm text-brasa-muted">{row.city}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
