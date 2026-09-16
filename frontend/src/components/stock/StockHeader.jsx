import { StockOverview } from "../StockDetail";

export function StockHeader({ data, trailing = null }) {
  return (
    <StockOverview
      data={data}
      headerTrailing={trailing}
      sectionIds={[]}
      showCustomizer={false}
    />
  );
}
