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
          <p>© 2025 Brasaland. All rights reserved.</p>
          <nav className="mt-4 flex flex-wrap gap-4 font-display text-sm font-semibold" aria-label="Footer">
            <Link to="/locations" className="text-white/80 no-underline hover:text-white">
              Locations
            </Link>
            <Link to="/brasa-points" className="text-white/80 no-underline hover:text-white">
              Brasa Points
            </Link>
            <Link to="/join" className="text-white/80 no-underline hover:text-white">
              Join
            </Link>
            <Link to="/#contact" className="text-white/80 no-underline hover:text-white">
              Contact
            </Link>
            <a
              href={brand.social.instagram}
              className="text-white/80 no-underline hover:text-white"
              rel="noreferrer"
              target="_blank"
            >
              Instagram
            </a>
            <a
              href={brand.social.facebook}
              className="text-white/80 no-underline hover:text-white"
              rel="noreferrer"
              target="_blank"
            >
              Facebook
            </a>
          </nav>
        </div>
        <p className="font-display text-sm tracking-wide md:text-right">
          {brand.contact.email}
          <br />
          Colombia {brand.contact.colombiaPhone} · Florida {brand.contact.floridaPhone}
        </p>
      </div>
    </footer>
  );
}
