import { Loader2 } from 'lucide-react';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
interface Props extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: 'md' | 'sm';
  loading?: boolean;
  block?: boolean;
  icon?: React.ReactNode;
}
export const Button: React.FC<Props> = ({ variant = 'secondary', size = 'md', loading, block, icon, children, disabled, className = '', type = 'button', ...rest }) => (
  <button
    type={type}
    className={`rn-btn rn-btn-${variant} rn-btn-${size}${block ? ' rn-btn-block' : ''} ${className}`.trim()}
    disabled={disabled || loading}
    aria-busy={loading || undefined}
    {...rest}
  >
    {loading ? <Loader2 size={15} className="rn-spin" aria-hidden="true" /> : icon}
    {children}
  </button>
);
