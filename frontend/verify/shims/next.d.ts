// Types-only stand-in for the `next` package (Metadata / Viewport used by app/layout.tsx).
declare module "next" {
  export type Metadata = { title?: string; description?: string; manifest?: string; robots?: { index?: boolean; follow?: boolean } };
  export type Viewport = { width?: string; initialScale?: number; themeColor?: string };
}
