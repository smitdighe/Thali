import { Fragment, useState } from "react";
import type { OptionResult, ScoredListing } from "../types";
import { etaText, ratingText, rupees } from "../format";
import DietMark from "./DietMark";

interface Props {
  options: OptionResult[];
}

function ListingDetail({ scored }: { scored: ScoredListing }) {
  return (
    <div className="listing-detail">
      <h3>
        {scored.listing.provider_label} · score {scored.score.toFixed(4)}
        {scored.feasible ? "" : " · not feasible"}
      </h3>
      {scored.factors.length > 0 ? (
        <table className="factors">
          <thead>
            <tr>
              <th scope="col">Factor</th>
              <th scope="col">Value</th>
              <th scope="col">Weight</th>
              <th scope="col">Points</th>
            </tr>
          </thead>
          <tbody>
            {scored.factors.map((factor) => (
              <tr key={factor.factor}>
                <td>{factor.factor}</td>
                <td>{factor.value.toFixed(4)}</td>
                <td>{factor.weight.toFixed(4)}</td>
                <td>{factor.points.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">Not scored.</p>
      )}
      <p className="muted">Bonus: {scored.bonus.toFixed(4)}</p>
      {scored.violations.length > 0 ? (
        <ul className="violations">
          {scored.violations.map((violation, index) => (
            <li key={index}>{violation}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default function OptionsTable({ options }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);
  const topScore = options.reduce((max, option) => Math.max(max, option.score), 0);

  function toggle(id: string) {
    setOpenId((current) => (current === id ? null : id));
  }

  return (
    <section aria-labelledby="options-heading">
      <h2 id="options-heading" className="section-title">
        Ranked options
      </h2>
      <div className="table-wrap">
        <table className="options">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Item / Restaurant (area)</th>
              <th scope="col">Sources</th>
              <th scope="col">Price</th>
              <th scope="col">Rating</th>
              <th scope="col">ETA</th>
              <th scope="col">Score</th>
            </tr>
          </thead>
          <tbody>
            {options.map((option) => {
              const listing = option.best.listing;
              const open = openId === option.option_id;
              const discounted =
                listing.price_paise !== null &&
                listing.effective_price_paise !== null &&
                listing.effective_price_paise < listing.price_paise;
              const width = topScore > 0 ? (option.score / topScore) * 100 : 0;
              return (
                <Fragment key={option.option_id}>
                  <tr className="option-row" onClick={() => toggle(option.option_id)}>
                    <td>{option.rank ?? ""}</td>
                    <td>
                      <button type="button" className="row-toggle" aria-expanded={open}>
                        <DietMark diet={listing.diet} /> <strong>{option.item}</strong>
                      </button>
                      <div className="muted">
                        {option.area ? `${option.restaurant} (${option.area})` : option.restaurant}
                      </div>
                    </td>
                    <td>
                      <span className="source-badges">
                        {option.listings.map((scored) => (
                          <span
                            key={scored.listing.listing_id}
                            className={scored.feasible ? "source-badge" : "source-badge infeasible"}
                            title={scored.violations.length > 0 ? scored.violations.join("; ") : undefined}
                          >
                            {scored.listing.provider_label}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td>
                      {discounted ? <span className="struck">{rupees(listing.price_paise)}</span> : null}{" "}
                      {rupees(listing.effective_price_paise ?? listing.price_paise)}
                    </td>
                    <td>{ratingText(listing.rating, listing.rating_count)}</td>
                    <td>{etaText(listing.eta_min_low, listing.eta_min_high)}</td>
                    <td>
                      <div className="score-cell">
                        <span className="score-track">
                          <span className="score-bar" style={{ width: `${width}%` }} />
                        </span>
                        <span>{option.score.toFixed(4)}</span>
                      </div>
                    </td>
                  </tr>
                  {open ? (
                    <tr className="detail-row">
                      <td colSpan={7}>
                        {option.listings.map((scored) => (
                          <ListingDetail key={scored.listing.listing_id} scored={scored} />
                        ))}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
