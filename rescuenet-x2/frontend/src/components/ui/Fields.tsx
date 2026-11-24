import { Search } from 'lucide-react';
import { useId } from 'react';

interface FieldProps { label: string; hint?: string; error?: string | null; children: (id: string, describedBy: string | undefined) => React.ReactNode }
/** Label + control + hint/error wiring in one place, so every form is labelled and announces errors. */
export const Field: React.FC<FieldProps> = ({ label, hint, error, children }) => {
  const id = useId();
  const desc = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  return (
    <div className="rn-field">
      <label htmlFor={id}>{label}</label>
      {children(id, desc)}
      {error ? <span id={`${id}-err`} className="rn-field-error" role="alert">{error}</span> : hint ? <span id={`${id}-hint`} className="rn-field-hint">{hint}</span> : null}
    </div>
  );
};

export const TextField: React.FC<{ label: string; hint?: string; error?: string | null } & React.InputHTMLAttributes<HTMLInputElement>> = ({ label, hint, error, ...rest }) => (
  <Field label={label} hint={hint} error={error}>
    {(id, desc) => <input id={id} className="rn-input" aria-describedby={desc} aria-invalid={error ? true : undefined} {...rest} />}
  </Field>
);

export const SelectField: React.FC<{ label: string; hint?: string; error?: string | null } & React.SelectHTMLAttributes<HTMLSelectElement>> = ({ label, hint, error, children, ...rest }) => (
  <Field label={label} hint={hint} error={error}>
    {(id, desc) => <select id={id} className="rn-input" aria-describedby={desc} {...rest}>{children}</select>}
  </Field>
);

export const SearchField: React.FC<{ value: string; onChange: (v: string) => void; placeholder?: string; label?: string }> = ({ value, onChange, placeholder = 'Search', label = 'Search' }) => (
  <div className="rn-search" role="search">
    <Search size={15} aria-hidden="true" />
    <input type="search" className="rn-input" aria-label={label} placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
  </div>
);
