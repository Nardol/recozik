import { ReactNode } from "react";
import { SkipLink } from "../../components/SkipLink";

interface Props {
  children: ReactNode;
}

export default function LocaleLayout({ children }: Props) {
  return (
    <>
      <SkipLink />
      <div id="main-content" tabIndex={-1}>
        {children}
      </div>
    </>
  );
}
