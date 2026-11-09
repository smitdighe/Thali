import type { Diet } from "../types";

interface Props {
  diet: Diet | null;
}

function classFor(diet: Diet | null): string {
  if (diet === "veg" || diet === "vegan") return "diet-mark diet-veg";
  if (diet === "non_veg") return "diet-mark diet-nonveg";
  if (diet === "egg") return "diet-mark diet-egg";
  return "diet-mark diet-unknown";
}

function titleFor(diet: Diet | null): string {
  if (diet === null) return "diet not listed";
  if (diet === "non_veg") return "non-veg";
  return diet;
}

export default function DietMark({ diet }: Props) {
  return <span className={classFor(diet)} title={titleFor(diet)} role="img" aria-label={titleFor(diet)} />;
}
