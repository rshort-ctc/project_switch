type PanelProps = {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
};

export function Panel({ title, action, children }: PanelProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{title}</h2>
        {action}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}
