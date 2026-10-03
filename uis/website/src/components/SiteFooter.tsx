import { Link } from "react-router-dom";
import { brand } from "../content/brand";

export function SiteFooter() {
  return (
    <footer className="bg-[#11100e] py-10 text-[0.95rem] text-white/70">
      <div className="mx-auto grid w-[min(100%-2rem,68rem)] gap-6 md:grid-cols-[1.4fr_1fr] md:items-end">
        <div>
          <Link
            to="/"
            className="mb-2 inline-block font-display text-xl font-bold text-white no-underline"
          >
            {brand.name}
          </Link>
          <p>
            Led by {brand.ceo}. Built for guests in Colombia and Florida —
            same grill, two markets.
          </p>
          <nav className="mt-4 flex flex-wrap gap-4 font-display text-sm font-semibold" aria-label="Footer">
            <Link to="/locations" className="text-white/80 no-underline hover:text-white">
              Locations
            </Link>
            <Link to="/brasa-points" className="text-white/80 no-underline hover:text-white">
              Brasa Points
            </Link>
          </nav>
        </div>
        <p className="font-display text-sm tracking-wide md:text-right">
          HQ {brand.hq} · Office {brand.miamiOffice}
        </p>
      </div>
    </footer>
  );
}
