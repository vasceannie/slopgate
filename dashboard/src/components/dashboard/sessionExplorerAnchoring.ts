export const MIN_SCROLL_DELTA = 1;
export const NEAR_TOP_THRESHOLD = 50;

export function findFirstVisibleRow(
    tableBody: HTMLTableSectionElement | null,
): HTMLElement | null {
    if (!tableBody) return null;
    const rows = tableBody.querySelectorAll("tr[data-session-id]");
    for (let i = 0; i < rows.length; i++) {
        const row = rows[i] as HTMLElement;
        const rect = row.getBoundingClientRect();
        if (rect.bottom > 0 && rect.top < window.innerHeight) {
            return row;
        }
    }
    return null;
}

export function determineAnchor({
    expanded,
    tableBody,
}: {
    expanded: string | null;
    tableBody: HTMLTableSectionElement | null;
}): { id: string; top: number } | null {
    let anchorEl: HTMLElement | null = null;
    if (expanded && tableBody) {
        anchorEl = tableBody.querySelector(
            `tr[data-session-id="${expanded}"]`,
        ) as HTMLElement | null;
    }
    if (!anchorEl && tableBody) {
        anchorEl = findFirstVisibleRow(tableBody);
    }
    if (anchorEl) {
        const id = anchorEl.getAttribute("data-session-id");
        if (id) {
            return {
                id,
                top: anchorEl.getBoundingClientRect().top,
            };
        }
    }
    return null;
}

export function calculateScrollAdjustment(
    anchorId: string | null,
    oldTop: number,
    tableBody: HTMLTableSectionElement | null,
    scrollY: number,
): number {
    if (!anchorId || !tableBody) return 0;
    const newEl = tableBody.querySelector(
        `tr[data-session-id="${anchorId}"]`,
    ) as HTMLElement | null;
    if (!newEl) return 0;

    const newTop = newEl.getBoundingClientRect().top;
    const delta = newTop - oldTop;

    if (Math.abs(delta) >= MIN_SCROLL_DELTA && scrollY > NEAR_TOP_THRESHOLD) {
        return delta;
    }
    return 0;
}
