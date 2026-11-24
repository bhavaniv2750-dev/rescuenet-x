import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './Button';

/** Client-side paging helper plus control. */
export function paginate<T>(items: T[], page: number, size: number): T[] { return items.slice((page - 1) * size, page * size); }
export const Pagination: React.FC<{ page: number; size: number; total: number; onPage: (p: number) => void }> = ({ page, size, total, onPage }) => {
  const pages = Math.max(1, Math.ceil(total / size));
  if (total <= size) return null;
  return (
    <nav className="rn-pager" aria-label="Pagination">
      <span className="rn-field-hint">{(page - 1) * size + 1}–{Math.min(page * size, total)} of {total}</span>
      <Button size="sm" icon={<ChevronLeft size={14} />} disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page" />
      <span aria-live="polite">Page {page} of {pages}</span>
      <Button size="sm" icon={<ChevronRight size={14} />} disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page" />
    </nav>
  );
};
