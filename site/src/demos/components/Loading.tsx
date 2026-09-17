export function Loading({ label }: { label: string }) {
  return (
    <div className="demo demo-loading">
      <span className="spinner-dot" />
      {label}
    </div>
  );
}
