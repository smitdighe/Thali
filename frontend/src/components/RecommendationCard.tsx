import type { Recommendation } from "../types";
import { etaText, ratingText, rupees } from "../format";
import DietMark from "./DietMark";

interface Props {
  recommendation: Recommendation;
}

export default function RecommendationCard({ recommendation }: Props) {
  const { option, summary, reasons, comparison, cheaper_alternative, also_on, caveats } = recommendation;
  const listing = option.best.listing;
  const discounted =
    listing.price_paise !== null &&
    listing.effective_price_paise !== null &&
    listing.effective_price_paise < listing.price_paise;
  const place = option.area ? `${option.restaurant} · ${option.area}` : option.restaurant;

  return (
    <section className="card recommendation" aria-labelledby="recommendation-heading">
      <p className="card-label">Recommendation</p>
      <div className="card-head">
        <h2 id="recommendation-heading" className="item-title">
          <DietMark diet={listing.diet} /> {listing.item}
        </h2>
        <span className="badge">via {listing.provider_label}</span>
      </div>
      <p className="muted">{place}</p>
      <p className="facts">
        {discounted ? <span className="struck">{rupees(listing.price_paise)}</span> : null}
        <strong>{rupees(listing.effective_price_paise ?? listing.price_paise)}</strong>
        <span>{ratingText(listing.rating, listing.rating_count)}</span>
        <span>{etaText(listing.eta_min_low, listing.eta_min_high)}</span>
      </p>
      <p>{summary}</p>
      <h3 className="sub-title">Why</h3>
      <ul>
        {reasons.map((reason, index) => (
          <li key={index}>{reason}</li>
        ))}
      </ul>
      {comparison ? <p className="muted">{comparison}</p> : null}
      {cheaper_alternative ? <p className="muted">{cheaper_alternative}</p> : null}
      {also_on.length > 0 ? (
        <ul className="muted">
          {also_on.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      ) : null}
      {caveats.length > 0 ? (
        <div className="caveats">
          <ul>
            {caveats.map((caveat, index) => (
              <li key={index}>{caveat}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
