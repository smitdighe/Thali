import type { WhatIf } from "../types";

interface Props {
  items: WhatIf[];
}

export default function WhatIfList({ items }: Props) {
  if (items.length === 0) return null;
  return (
    <section className="card" aria-labelledby="whatif-heading">
      <h2 id="whatif-heading" className="section-title">
        What would change the pick
      </h2>
      <ul className="whatif-list">
        {items.map((item, index) => (
          <li key={index}>{item.statement}</li>
        ))}
      </ul>
    </section>
  );
}
