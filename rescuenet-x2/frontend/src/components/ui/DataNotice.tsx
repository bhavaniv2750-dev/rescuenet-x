import { ProvenanceBadge } from './Badges';

/** Honest provenance strip: says how many of the shown records are SIMULATED demonstration data (and therefore not real emergencies).
 *  Renders nothing when none are simulated. */
export const DataNotice: React.FC<{ items: { data_label?: string }[]; noun: string }> = ({ items, noun }) => {
  const sim = items.filter((i) => (i.data_label || '').toUpperCase() === 'SIMULATED').length;
  if (!sim) return null;
  return (
    <div className="data-notice" role="note">
      <ProvenanceBadge kind="SIMULATED" />
      <span>{sim} of {items.length} {noun} are simulated demonstration data, not real events. Do not treat them as real emergencies.</span>
    </div>
  );
};
