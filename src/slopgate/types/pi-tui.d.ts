// Minimal type stubs for @earendil-works/pi-tui used by slopgate Pi extension template.
// The real types are available at runtime inside Pi; this file exists solely so the
// TypeScript LSP can resolve imports without cascading into garbage errors.

declare module "@earendil-works/pi-tui" {
  export class Box {
    constructor(width: number, height: number, bg?: (text: string) => string)
    addChild(child: Text): void
  }

  export class Text {
    constructor(content: string, x: number, y: number)
  }

  export interface PiMessageRenderOptions {
    expanded?: boolean
    [key: string]: unknown
  }
}
