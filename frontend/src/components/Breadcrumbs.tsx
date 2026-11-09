interface Props {
  labels: string[];
  current: number;
  onSelect: (index: number) => void;
}

export default function Breadcrumbs({ labels, current, onSelect }: Props) {
  if (labels.length < 2) return null;
  return (
    <nav aria-label="Request history" className="crumbs">
      <ol>
        {labels.map((label, index) => (
          <li key={index}>
            {index > 0 ? <span className="crumb-sep" aria-hidden="true">›</span> : null}
            <button
              type="button"
              className="crumb"
              aria-current={index === current ? "step" : undefined}
              onClick={() => onSelect(index)}
            >
              {label}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
