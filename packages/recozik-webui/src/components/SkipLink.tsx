interface SkipLinkProps {
  label: string;
}

export function SkipLink({ label }: SkipLinkProps) {
  return (
    <a className="visually-hidden" href="#main-content">
      {label}
    </a>
  );
}
