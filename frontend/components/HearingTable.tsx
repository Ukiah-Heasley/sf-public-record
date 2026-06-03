import Link from "next/link";

type HearingTableRow = {
  hearing_id: string;
  hearing_date: string;
  title: string | null;
  status: string | null;
  document_count: number;
  agenda_item_count: number;
};

export function HearingTable({ hearings }: { hearings: HearingTableRow[] }) {
  if (!hearings.length) {
    return <div className="empty">No hearings indexed.</div>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Hearing</th>
            <th>Status</th>
            <th>Documents</th>
            <th>Items</th>
          </tr>
        </thead>
        <tbody>
          {hearings.map((hearing) => (
            <tr key={hearing.hearing_id}>
              <td>{formatDate(hearing.hearing_date)}</td>
              <td>
                <Link href={`/hearings/${hearing.hearing_id}`}>
                  {hearing.title ?? "Planning Commission"}
                </Link>
              </td>
              <td>
                <span className="badge">{hearing.status ?? "unknown"}</span>
              </td>
              <td>{hearing.document_count}</td>
              <td>{hearing.agenda_item_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  }).format(new Date(`${value}T00:00:00`));
}
