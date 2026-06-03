type BarDatum = {
  label: string;
  value: number;
};

export function Bars({ data }: { data: BarDatum[] }) {
  const max = Math.max(1, ...data.map((item) => item.value));

  if (!data.length) {
    return <div className="empty">No data indexed.</div>;
  }

  return (
    <div className="bars">
      {data.map((item) => {
        const width = item.value === 0 ? 0 : Math.max(3, (item.value / max) * 100);

        return (
          <div className="bar-row" key={item.label}>
            <div className="bar-label">
              <span>{item.label}</span>
              <strong>{item.value.toLocaleString()}</strong>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
