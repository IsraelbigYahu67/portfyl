import { StockOverview } from "../StockDetail";

export function StockHeader({ data, trailing = null }) {
  return (
    <StockOverview
      data={data}
      headerTrailing={trailing}
      headerHeadingLevel={1}
      sectionIds={[]}
      showCustomizer={false}
    />
  );
}
