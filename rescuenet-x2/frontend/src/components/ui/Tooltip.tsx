import { useId } from 'react';

/** CSS tooltip that also works for keyboard users (shown on focus) and screen readers (aria-describedby). */
export const Tooltip: React.FC<{ text: string; children: React.ReactNode }> = ({ text, children }) => {
  const id = useId();
  return (
    <span className="rn-tip" tabIndex={0} aria-describedby={id}>
      {children}
      <span role="tooltip" id={id} className="rn-tip-bubble">{text}</span>
    </span>
  );
};
