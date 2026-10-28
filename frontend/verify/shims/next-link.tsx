// Verification stand-in for next/link: client-side navigation via the History API.
import { type AnchorHTMLAttributes, type MouseEvent, type ReactNode } from "react";
import { navigate } from "./router-core";

type Props = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { href: string; children?: ReactNode; prefetch?: boolean };

export default function Link(props: Props) {
  // `prefetch` is accepted for API compatibility and not passed to the DOM.
  const { href, children, onClick, ...rest } = props;
  delete (rest as { prefetch?: boolean }).prefetch;
  function handle(e: MouseEvent<HTMLAnchorElement>) {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || rest.target === "_blank") return;
    if (!href.startsWith("/")) return;
    e.preventDefault();
    navigate(href);
  }
  return <a href={href} onClick={handle} {...rest}>{children}</a>;
}
