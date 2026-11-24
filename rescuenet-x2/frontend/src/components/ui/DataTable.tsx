import { EmptyState } from './States';

export interface Column<T> { key: string; header: string; render: (row: T) => React.ReactNode; className?: string }
/** Responsive table: scrolls inside its own container (never the page), real <th scope>, optional row action. */
export function DataTable<T>({ columns, rows, rowKey, empty = 'Nothing to show.', caption, onRowClick }: {
  columns: Column<T>[]; rows: T[]; rowKey: (r: T) => string | number; empty?: string; caption: string; onRowClick?: (r: T) => void;
}) {
  if (!rows.length) return <EmptyState title={empty} />;
  return (
    <div className="rn-table-wrap" tabIndex={0} role="region" aria-label={caption}>
      <table className="rn-table">
        <caption className="rn-sr">{caption}</caption>
        <thead><tr>{columns.map((c) => <th key={c.key} scope="col" className={c.className}>{c.header}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)} className={onRowClick ? 'rn-row-click' : undefined} onClick={onRowClick ? () => onRowClick(r) : undefined}>
              {columns.map((c) => <td key={c.key} className={c.className}>{c.render(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
