import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

function getDaysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfWeek(year, month) {
  // 0 = Sunday, we want Monday = 0
  const day = new Date(year, month, 1).getDay();
  return day === 0 ? 6 : day - 1;
}

function getPnlColor(pnl) {
  if (pnl === 0 || pnl == null) return "bg-slate-50";
  if (pnl > 0) {
    if (pnl >= 500) return "bg-emerald-300";
    if (pnl >= 200) return "bg-emerald-200";
    if (pnl >= 50) return "bg-emerald-100";
    return "bg-emerald-50";
  }
  if (pnl <= -500) return "bg-red-300";
  if (pnl <= -200) return "bg-red-200";
  if (pnl <= -50) return "bg-red-100";
  return "bg-red-50";
}

function getPnlTextColor(pnl) {
  if (pnl == null || pnl === 0) return "text-slate-400";
  return pnl > 0 ? "text-emerald-700" : "text-red-700";
}

function formatPnl(pnl) {
  if (pnl == null) return "";
  const sign = pnl >= 0 ? "+" : "";
  if (Math.abs(pnl) >= 1000) {
    return `${sign}$${(pnl / 1000).toFixed(1)}k`;
  }
  return `${sign}$${pnl.toFixed(0)}`;
}

const DAY_HEADERS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function OptionsCalendar({ data = [] }) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [selectedDay, setSelectedDay] = useState(null);

  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfWeek(year, month);

  // Build lookup from date string to data
  const dataMap = {};
  data.forEach((item) => {
    dataMap[item.date] = item;
  });

  // Build calendar cells
  const cells = [];
  // Empty cells before first day
  for (let i = 0; i < firstDay; i++) {
    cells.push(null);
  }
  // Day cells
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ day: d, date: dateStr, ...(dataMap[dateStr] || { pnl: null, trades_count: 0 }) });
  }

  const monthlyTotal = data
    .filter((item) => {
      const d = new Date(item.date);
      return d.getFullYear() === year && d.getMonth() === month;
    })
    .reduce((sum, item) => sum + (item.pnl || 0), 0);

  const monthlyTrades = data
    .filter((item) => {
      const d = new Date(item.date);
      return d.getFullYear() === year && d.getMonth() === month;
    })
    .reduce((sum, item) => sum + (item.trades_count || 0), 0);

  function prevMonth() {
    setSelectedDay(null);
    if (month === 0) {
      setMonth(11);
      setYear(year - 1);
    } else {
      setMonth(month - 1);
    }
  }

  function nextMonth() {
    setSelectedDay(null);
    if (month === 11) {
      setMonth(0);
      setYear(year + 1);
    } else {
      setMonth(month + 1);
    }
  }

  const monthName = new Date(year, month).toLocaleString("en-US", { month: "long", year: "numeric" });

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      {/* Header with navigation */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={prevMonth}
          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-700 transition-colors"
        >
          <ChevronLeft size={18} />
        </button>
        <h3 className="text-sm font-semibold text-slate-800">{monthName}</h3>
        <button
          onClick={nextMonth}
          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-700 transition-colors"
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {/* Day headers */}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {DAY_HEADERS.map((d) => (
          <div key={d} className="text-center text-[10px] font-semibold text-slate-400 uppercase py-1">
            {d}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-1">
        {cells.map((cell, idx) => {
          if (!cell) {
            return <div key={`empty-${idx}`} className="min-h-[60px]" />;
          }
          const hasTrades = cell.trades_count > 0;
          const isSelected = selectedDay === cell.day;

          return (
            <div
              key={cell.date}
              onClick={() => hasTrades && setSelectedDay(isSelected ? null : cell.day)}
              className={`
                min-h-[60px] rounded-lg p-1.5 flex flex-col items-center justify-center gap-0.5
                transition-all border
                ${hasTrades ? "cursor-pointer hover:ring-2 hover:ring-brand/30" : "cursor-default"}
                ${isSelected ? "ring-2 ring-brand border-brand" : "border-transparent"}
                ${getPnlColor(cell.pnl)}
              `}
            >
              <span className="text-[11px] font-medium text-slate-600">{cell.day}</span>
              {hasTrades && (
                <>
                  <span className={`text-[10px] font-bold tabular-nums ${getPnlTextColor(cell.pnl)}`}>
                    {formatPnl(cell.pnl)}
                  </span>
                  <span className="text-[9px] text-slate-400">
                    {cell.trades_count} {cell.trades_count === 1 ? "trade" : "trades"}
                  </span>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Selected day detail */}
      {selectedDay && (
        <div className="mt-3 p-3 rounded-lg bg-slate-50 border border-surface-border">
          <p className="text-xs text-slate-500">
            {new Date(year, month, selectedDay).toLocaleDateString("en-US", {
              weekday: "long",
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
          </p>
          {(() => {
            const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(selectedDay).padStart(2, "0")}`;
            const dayData = dataMap[dateStr];
            if (!dayData) return null;
            return (
              <div className="flex items-center gap-4 mt-1.5">
                <span className={`text-sm font-bold ${dayData.pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                  {dayData.pnl >= 0 ? "+" : ""}${dayData.pnl?.toFixed(2)}
                </span>
                <span className="text-xs text-slate-500">
                  {dayData.trades_count} {dayData.trades_count === 1 ? "trade" : "trades"} closed
                </span>
              </div>
            );
          })()}
        </div>
      )}

      {/* Monthly total */}
      <div className="mt-4 pt-3 border-t border-surface-border flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500">Monthly Total</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400">{monthlyTrades} trades</span>
          <span className={`text-sm font-bold tabular-nums ${monthlyTotal >= 0 ? "text-emerald-600" : "text-red-600"}`}>
            {monthlyTotal >= 0 ? "+" : ""}${monthlyTotal.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  );
}
