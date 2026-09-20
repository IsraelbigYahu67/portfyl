import { useNavigate } from "react-router-dom";

export function useStockDetail() {
  const navigate = useNavigate();
  return {
    openStock: (ticker) => {
      if (!ticker) return;
      navigate(`/stock/${encodeURIComponent(String(ticker).toUpperCase())}`);
    },
  };
}
