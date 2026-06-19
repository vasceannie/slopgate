/**
 * Ambient type declarations for @earendil-works/pi-tui.
 *
 * This package is a Pi platform dependency installed alongside the extension
 * at ~/.pi/agent/extensions/pi-slopgate/.  During development in the slopgate
 * source tree the package is not available, so we declare the subset of types
 * used by the pi_extension template here.
 */

declare module "@earendil-works/pi-tui" {
  export class Text {
    constructor(content: string, x: number, y: number)
  }

  export class Box {
    constructor(
      x: number,
      y: number,
      renderCallback: (text: string) => string,
    )
    addChild(child: Text): void
  }
}
