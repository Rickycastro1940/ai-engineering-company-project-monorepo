import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { SiteFooter } from "../components/SiteFooter";
import { SiteHeader } from "../components/SiteHeader";
import {
  COUNTRIES,
  DIETARY_OPTIONS,
  HOW_FOUND_OPTIONS,
  ORDERING_NOTE,
  SUCCESS_BODY,
  SUCCESS_TITLE,
} from "../content/loyaltySignup";
import {
  citiesFor,
  emptyLoyaltyForm,
  locationsFor,
  validateLoyaltyForm,
  type FieldErrors,
  type LoyaltyFormValues,
} from "../lib/validateLoyaltyForm";

const fieldClass =
  "mt-1 w-full rounded-[0.35rem] border border-brasa-charcoal/20 bg-white px-3 py-3 text-base text-brasa-ink outline-none focus:border-brasa-ember focus:ring-2 focus:ring-brasa-ember/30";
const errorClass = "mt-1 text-sm font-semibold text-brasa-ember-deep";
const labelClass = "font-display text-sm font-semibold text-brasa-charcoal";

export function JoinPage() {
  const [values, setValues] = useState<LoyaltyFormValues>(emptyLoyaltyForm);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [touched, setTouched] = useState<Partial<Record<keyof LoyaltyFormValues, boolean>>>({});
  const [submittedOk, setSubmittedOk] = useState(false);

  const cityOptions = useMemo(() => citiesFor(values.country), [values.country]);
  const locationOptions = useMemo(() => locationsFor(values.city), [values.city]);

  function setField<K extends keyof LoyaltyFormValues>(key: K, value: LoyaltyFormValues[K]) {
    setValues((current) => {
      const next = { ...current, [key]: value };
      if (key === "country") {
        next.city = "";
        next.favoriteLocation = "";
      }
      if (key === "city") {
        next.favoriteLocation = "";
      }
      return next;
    });
    setSubmittedOk(false);
  }

  function validateField(key: keyof LoyaltyFormValues, snapshot?: LoyaltyFormValues) {
    const nextErrors = validateLoyaltyForm(snapshot ?? values);
    setErrors((current) => {
      const copy = { ...current };
      if (nextErrors[key]) {
        copy[key] = nextErrors[key];
      } else {
        delete copy[key];
      }
      return copy;
    });
  }

  function handleBlur(key: keyof LoyaltyFormValues) {
    setTouched((current) => ({ ...current, [key]: true }));
    validateField(key);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validateLoyaltyForm(values);
    setErrors(nextErrors);
    setTouched({
      fullName: true,
      email: true,
      phone: true,
      country: true,
      city: true,
      howFound: true,
      dateOfBirth: true,
      acceptTerms: true,
    });
    if (Object.keys(nextErrors).length > 0) {
      setSubmittedOk(false);
      return;
    }
    setSubmittedOk(true);
  }

  function handleClear() {
    setValues(emptyLoyaltyForm());
    setErrors({});
    setTouched({});
    setSubmittedOk(false);
  }

  function toggleDietary(option: string) {
    setField(
      "dietary",
      values.dietary.includes(option)
        ? values.dietary.filter((item) => item !== option)
        : [...values.dietary, option],
    );
  }

  return (
    <>
      <SiteHeader />
      <main id="main-content" className="bg-brasa-paper">
        <div className="mx-auto w-[min(100%-2rem,40rem)] py-12 md:py-16">
          <p className="mb-3 font-display text-sm font-semibold uppercase tracking-[0.08em] text-brasa-ember">
            Brasa Points
          </p>
          <h1 className="mb-3 text-[clamp(1.85rem,4vw,2.5rem)]">Join the loyalty programme</h1>
          <p className="mb-4 text-lg text-brasa-muted">
            Register for digital Brasa Points. Earn 1 point for every $10,000 COP or $5 USD and redeem
            at any of our 14 locations. Guests must be 18 or older.
          </p>
          <p
            className="mb-8 rounded-[0.35rem] border border-brasa-teal/30 bg-brasa-teal/10 px-4 py-3 text-sm text-brasa-charcoal"
            role="note"
          >
            {ORDERING_NOTE}
          </p>

          {submittedOk ? (
            <div
              className="rounded-[0.5rem] border border-brasa-leaf/40 bg-brasa-leaf/10 p-6"
              role="status"
              aria-live="polite"
            >
              <h2 className="mb-3 text-2xl text-brasa-leaf">{SUCCESS_TITLE}</h2>
              <p className="text-brasa-ink">{SUCCESS_BODY}</p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link
                  to="/locations"
                  className="inline-flex rounded-[0.35rem] bg-brasa-ember px-4 py-3 font-display text-sm font-semibold text-white no-underline hover:bg-brasa-ember-deep"
                >
                  Find a location
                </Link>
                <button
                  type="button"
                  onClick={handleClear}
                  className="inline-flex rounded-[0.35rem] border border-brasa-charcoal/20 bg-white px-4 py-3 font-display text-sm font-semibold"
                >
                  Register another guest
                </button>
              </div>
            </div>
          ) : (
            <form className="grid gap-5" onSubmit={handleSubmit} noValidate>
              <fieldset className="grid gap-5 rounded-[0.5rem] border border-brasa-charcoal/10 bg-white p-5 md:p-6">
                <legend className="px-1 font-display text-base font-bold text-brasa-charcoal">
                  Your details
                </legend>
                <div>
                  <label className={labelClass} htmlFor="fullName">
                    Full name
                  </label>
                  <input
                    id="fullName"
                    name="fullName"
                    type="text"
                    autoComplete="name"
                    required
                    className={fieldClass}
                    value={values.fullName}
                    onChange={(event) => setField("fullName", event.target.value)}
                    onBlur={() => handleBlur("fullName")}
                    aria-invalid={Boolean(touched.fullName && errors.fullName)}
                    aria-describedby={errors.fullName ? "fullName-error" : undefined}
                  />
                  {touched.fullName && errors.fullName ? (
                    <p id="fullName-error" className={errorClass} role="alert">
                      {errors.fullName}
                    </p>
                  ) : null}
                </div>
                <div>
                  <label className={labelClass} htmlFor="email">
                    Email
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    className={fieldClass}
                    value={values.email}
                    onChange={(event) => setField("email", event.target.value)}
                    onBlur={() => handleBlur("email")}
                    aria-invalid={Boolean(touched.email && errors.email)}
                    aria-describedby={errors.email ? "email-error" : undefined}
                  />
                  {touched.email && errors.email ? (
                    <p id="email-error" className={errorClass} role="alert">
                      {errors.email}
                    </p>
                  ) : null}
                </div>
                <div>
                  <label className={labelClass} htmlFor="phone">
                    Phone
                  </label>
                  <input
                    id="phone"
                    name="phone"
                    type="tel"
                    autoComplete="tel"
                    required
                    placeholder="+57 300 123 4567"
                    className={fieldClass}
                    value={values.phone}
                    onChange={(event) => setField("phone", event.target.value)}
                    onBlur={() => handleBlur("phone")}
                    aria-invalid={Boolean(touched.phone && errors.phone)}
                    aria-describedby={errors.phone ? "phone-error" : undefined}
                  />
                  {touched.phone && errors.phone ? (
                    <p id="phone-error" className={errorClass} role="alert">
                      {errors.phone}
                    </p>
                  ) : null}
                </div>
                <div>
                  <label className={labelClass} htmlFor="dateOfBirth">
                    Date of birth
                  </label>
                  <input
                    id="dateOfBirth"
                    name="dateOfBirth"
                    type="date"
                    required
                    className={fieldClass}
                    value={values.dateOfBirth}
                    onChange={(event) => setField("dateOfBirth", event.target.value)}
                    onBlur={() => handleBlur("dateOfBirth")}
                    aria-invalid={Boolean(touched.dateOfBirth && errors.dateOfBirth)}
                    aria-describedby={errors.dateOfBirth ? "dob-error" : undefined}
                  />
                  {touched.dateOfBirth && errors.dateOfBirth ? (
                    <p id="dob-error" className={errorClass} role="alert">
                      {errors.dateOfBirth}
                    </p>
                  ) : null}
                </div>
              </fieldset>

              <fieldset className="grid gap-5 rounded-[0.5rem] border border-brasa-charcoal/10 bg-white p-5 md:p-6">
                <legend className="px-1 font-display text-base font-bold text-brasa-charcoal">
                  Where you visit
                </legend>
                <div>
                  <label className={labelClass} htmlFor="country">
                    Country
                  </label>
                  <select
                    id="country"
                    name="country"
                    required
                    className={fieldClass}
                    value={values.country}
                    onChange={(event) => setField("country", event.target.value)}
                    onBlur={() => handleBlur("country")}
                    aria-invalid={Boolean(touched.country && errors.country)}
                  >
                    <option value="">Select your country</option>
                    {COUNTRIES.map((country) => (
                      <option key={country} value={country}>
                        {country}
                      </option>
                    ))}
                  </select>
                  {touched.country && errors.country ? (
                    <p className={errorClass} role="alert">
                      {errors.country}
                    </p>
                  ) : null}
                </div>
                <div>
                  <label className={labelClass} htmlFor="city">
                    City
                  </label>
                  <select
                    id="city"
                    name="city"
                    required
                    className={fieldClass}
                    value={values.city}
                    disabled={!values.country}
                    onChange={(event) => setField("city", event.target.value)}
                    onBlur={() => handleBlur("city")}
                    aria-invalid={Boolean(touched.city && errors.city)}
                  >
                    <option value="">Select your city</option>
                    {cityOptions.map((city) => (
                      <option key={city} value={city}>
                        {city}
                      </option>
                    ))}
                  </select>
                  {touched.city && errors.city ? (
                    <p className={errorClass} role="alert">
                      {errors.city}
                    </p>
                  ) : null}
                </div>
                <div>
                  <label className={labelClass} htmlFor="favoriteLocation">
                    Favorite Brasaland location <span className="font-normal text-brasa-muted">(optional)</span>
                  </label>
                  <select
                    id="favoriteLocation"
                    name="favoriteLocation"
                    className={fieldClass}
                    value={values.favoriteLocation}
                    disabled={!values.city}
                    onChange={(event) => setField("favoriteLocation", event.target.value)}
                  >
                    <option value="">Select a location</option>
                    {locationOptions.map((location) => (
                      <option key={location} value={location}>
                        {location}
                      </option>
                    ))}
                  </select>
                </div>
              </fieldset>

              <fieldset className="grid gap-5 rounded-[0.5rem] border border-brasa-charcoal/10 bg-white p-5 md:p-6">
                <legend className="px-1 font-display text-base font-bold text-brasa-charcoal">
                  Preferences
                </legend>
                <div>
                  <p className={labelClass} id="dietary-label">
                    Dietary preferences <span className="font-normal text-brasa-muted">(optional)</span>
                  </p>
                  <div className="mt-3 grid gap-2" role="group" aria-labelledby="dietary-label">
                    {DIETARY_OPTIONS.map((option) => (
                      <label key={option} className="flex items-center gap-3 text-base">
                        <input
                          type="checkbox"
                          checked={values.dietary.includes(option)}
                          onChange={() => toggleDietary(option)}
                          className="size-4 accent-brasa-ember"
                        />
                        {option}
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <label className={labelClass} htmlFor="howFound">
                    How did you find us?
                  </label>
                  <select
                    id="howFound"
                    name="howFound"
                    required
                    className={fieldClass}
                    value={values.howFound}
                    onChange={(event) => setField("howFound", event.target.value)}
                    onBlur={() => handleBlur("howFound")}
                    aria-invalid={Boolean(touched.howFound && errors.howFound)}
                  >
                    <option value="">Select an option</option>
                    {HOW_FOUND_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                  {touched.howFound && errors.howFound ? (
                    <p className={errorClass} role="alert">
                      {errors.howFound}
                    </p>
                  ) : null}
                </div>
                <label className="flex items-start gap-3 text-base">
                  <input
                    type="checkbox"
                    checked={values.acceptTerms}
                    onChange={(event) => setField("acceptTerms", event.target.checked)}
                    onBlur={() => handleBlur("acceptTerms")}
                    className="mt-1 size-4 accent-brasa-ember"
                    required
                    aria-invalid={Boolean(touched.acceptTerms && errors.acceptTerms)}
                  />
                  <span>I accept the Brasa Points program terms</span>
                </label>
                {touched.acceptTerms && errors.acceptTerms ? (
                  <p className={errorClass} role="alert">
                    {errors.acceptTerms}
                  </p>
                ) : null}
                <label className="flex items-start gap-3 text-base">
                  <input
                    type="checkbox"
                    checked={values.receiveOffers}
                    onChange={(event) => setField("receiveOffers", event.target.checked)}
                    className="mt-1 size-4 accent-brasa-ember"
                  />
                  <span>I want to receive offers via email</span>
                </label>
              </fieldset>

              <div className="flex flex-wrap gap-3">
                <button
                  type="submit"
                  className="inline-flex min-h-12 items-center justify-center rounded-[0.35rem] bg-brasa-ember px-5 py-3 font-display text-[0.95rem] font-semibold text-white hover:bg-brasa-ember-deep focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brasa-ember"
                >
                  Join Brasa Points
                </button>
                <button
                  type="button"
                  onClick={handleClear}
                  className="inline-flex min-h-12 items-center justify-center rounded-[0.35rem] border border-brasa-charcoal/25 bg-white px-5 py-3 font-display text-[0.95rem] font-semibold text-brasa-charcoal hover:bg-brasa-stone"
                >
                  Clear form
                </button>
              </div>
            </form>
          )}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
