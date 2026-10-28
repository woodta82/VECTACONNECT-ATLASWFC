// Verification stand-in for next/image (the harness cannot install Next.js). Renders the same <img>
// Next emits for `unoptimized` images: explicit width/height, lazy loading unless `priority`.
import type { ImgHTMLAttributes } from "react";

type Props = Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "width" | "height" | "loading"> & {
  src: string; alt: string; width: number; height: number; priority?: boolean; unoptimized?: boolean;
};

export default function Image(props: Props) {
  // `unoptimized` is accepted for API compatibility and not passed to the DOM.
  const { src, alt, width, height, priority, ...rest } = props;
  delete (rest as { unoptimized?: boolean }).unoptimized;
  // eslint-disable-next-line @next/next/no-img-element -- this file IS the image component stand-in
  return <img src={src} alt={alt} width={width} height={height} loading={priority ? "eager" : "lazy"} decoding="async" {...rest} />;
}
