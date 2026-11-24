import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Button, ConfirmDialog, DataTable, Dialog, EmptyState, Pagination, paginate, ProvenanceBadge, SeverityBadge, Tabs, TextField } from './index';

describe('SeverityBadge', () => {
  it('shows a text label and an icon, never colour alone', () => {
    const { container } = render(<SeverityBadge severity="CRITICAL" />);
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeNull();
  });
  it('gives each level a different shape', () => {
    const shapes = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW'].map((s) => render(<SeverityBadge severity={s} />).container.innerHTML.match(/lucide-([a-z-]+)/)?.[1]);
    expect(new Set(shapes).size).toBe(4);
  });
  it('does not invent a severity', () => {
    render(<SeverityBadge severity="WEIRD" />);
    expect(screen.getByText('WEIRD')).toBeInTheDocument();
  });
});

describe('ProvenanceBadge', () => {
  it('renders the label as text and explains it', () => {
    render(<ProvenanceBadge kind="SIMULATED" />);
    expect(screen.getByText('SIMULATED')).toHaveAttribute('title', expect.stringMatching(/not a real/i));
  });
});

describe('Button', () => {
  it('is disabled and busy while loading, and does not fire', async () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>Save</Button>);
    const b = screen.getByRole('button', { name: 'Save' });
    expect(b).toBeDisabled(); expect(b).toHaveAttribute('aria-busy', 'true');
    await userEvent.click(b); expect(onClick).not.toHaveBeenCalled();
  });
});

describe('TextField', () => {
  it('links label, hint and error for assistive technology', () => {
    render(<TextField label="Email" error="Enter a valid address" />);
    const input = screen.getByLabelText('Email');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input.getAttribute('aria-describedby')).toBeTruthy();
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a valid address');
  });
});

describe('Dialog', () => {
  it('moves focus in, closes on Escape and returns focus to the opener', async () => {
    function Host() {
      const [open, setOpen] = useState(false);
      return <><button onClick={() => setOpen(true)}>Open</button><Dialog open={open} title="Edit" onClose={() => setOpen(false)}><input aria-label="Name" /></Dialog></>;
    }
    render(<Host />);
    const opener = screen.getByRole('button', { name: 'Open' });
    await userEvent.click(opener);
    expect(screen.getByRole('dialog', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
  });
  it('keeps Tab inside the dialog', async () => {
    render(<Dialog open title="T" onClose={() => {}}><input aria-label="a" /></Dialog>);
    for (let i = 0; i < 5; i++) await userEvent.tab();
    expect(screen.getByRole('dialog').contains(document.activeElement)).toBe(true);
  });
});

describe('ConfirmDialog', () => {
  it('does nothing until confirmed and names the action', async () => {
    const onConfirm = vi.fn(); const onCancel = vi.fn();
    render(<ConfirmDialog open title="Approve dispatch" message="Send the team?" confirmLabel="Approve and dispatch" onConfirm={onConfirm} onCancel={onCancel} />);
    expect(onConfirm).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Approve and dispatch' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalled();
  });
});

describe('Tabs', () => {
  it('moves with the arrow keys', async () => {
    function Host() { const [v, setV] = useState<'a' | 'b'>('a'); return <Tabs label="Sections" tabs={[{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }]} value={v} onChange={setV} />; }
    render(<Host />);
    screen.getByRole('tab', { name: 'A' }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'B' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('DataTable, EmptyState, Pagination', () => {
  it('shows the empty message instead of an empty table', () => {
    render(<DataTable caption="Incidents" columns={[]} rows={[]} rowKey={() => 1} empty="No incidents." />);
    expect(screen.getByText('No incidents.')).toBeInTheDocument(); expect(screen.queryByRole('table')).toBeNull();
  });
  it('renders captioned rows with column headers', () => {
    render(<DataTable caption="Teams" columns={[{ key: 'n', header: 'Name', render: (r: { n: string }) => r.n }]} rows={[{ n: 'Alpha' }]} rowKey={(r) => r.n} />);
    expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument(); expect(screen.getByText('Alpha')).toBeInTheDocument();
  });
  it('pages without losing items', () => {
    const items = Array.from({ length: 23 }, (_, i) => i);
    expect(paginate(items, 1, 10)).toHaveLength(10); expect(paginate(items, 3, 10)).toHaveLength(3);
    const onPage = vi.fn(); render(<Pagination page={1} size={10} total={23} onPage={onPage} />);
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
  });
  it('empty state announces itself politely', () => { render(<EmptyState title="Nothing here" />); expect(screen.getByRole('status')).toHaveTextContent('Nothing here'); });
});
