# UI Layout Optimization - Domains Page

**Date:** 2026-03-06
**Status:** Complete

## Overview

Optimized the `/domains` page UI for small data volumes and improved usability through layout consolidation and better scrolling behavior.

## Changes Made

### 1. IP Pools Panel - Horizontal Layout

- **Before:** Three text areas (Source IPs, Destination IPs, Services) stacked vertically
- **After:** All three text areas in a single horizontal row
- **Benefit:** Better use of horizontal space, compact layout

### 2. Card Layout - Full Width, Vertical Stacking

- **Before:** Fixed 400px width cards in horizontal scroll container
- **After:** 100% width cards, vertically stacked with scrolling
- **Benefit:** Each card uses full page width, easier to read and edit

### 3. Card Line Layout

- **Before:** Label and fields in same horizontal line
- **After:** Label above fields (column layout), all fields in one row
- **Benefit:** More space for dropdowns, cleaner presentation

### 4. Submit Confirmation

- **Added:** Modal confirmation dialog before rule submission
- **Message:** "Create X card(s) with Y firewall rules?"
- **Benefit:** Prevents accidental submissions

### 5. Button Layout

- **Before:** Submit button in separate section at bottom
- **After:** Submit button on same row as Add Card (right side)
- **Benefit:** More compact, accessible layout

### 6. Scrolling Behavior

- **IP Pools Panel:** Always visible (collapsed or expanded)
- **Cards Area:** Scrollable only
- **Loading Spinner:** Fullscreen overlay (no layout interference)
- **Benefit:** Better space utilization, always-accessible controls

### 7. Dropdown Sizing

- **Regular selects:** 150px min-width (was 100px)
- **Small selects (Action/Track):** 105px min-width (was 70px)
- **Benefit:** More readable content

## Technical Details

### CSS Key Changes

**Fixed flex container scrolling:**

```css
/* Added min-height: 0 to all nested flex containers */
.pageContainer, .container, .cardsWrapper, .cardsScroll {
  min-height: 0;  /* Critical for flex overflow */
}
```

**Card overlap fix:**

```css
.card {
  flex-shrink: 0;     /* Prevent card compression */
  position: relative;
  z-index: 1;         /* Proper stacking context */
}
```

### Modified Files

**Styles:**

- `webui/src/styles/components/ipPoolsPanel.module.css`
- `webui/src/styles/components/ruleCard.module.css`
- `webui/src/styles/components/cardsContainer.module.css`
- `webui/src/styles/pages/domains.module.css`

**Components:**

- `webui/src/components/IpPoolsPanel.tsx` - Reduced textarea rows to 3
- `webui/src/components/CardsContainer.tsx` - Added header row with both buttons
- `webui/src/pages/Domains.tsx` - Modal confirm, fullscreen spinner

## Layout Structure

```
┌─────────────────────────────────────────────────────┐
│ IP Pools Panel (always visible)                     │
│ [Source IPs] [Dest IPs] [Services] - horizontal    │
├─────────────────────────────────────────────────────┤
│ [Add Card].........................[Submit Rules]   │
├─────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────┐  │
│ │ Card 1 - Source line (full width)            │  │
│ │         Destination line (full width)          │  │
│ ├───────────────────────────────────────────────┤  │
│ │ Card 2 - Source line (full width)            │  │
│ │         Destination line (full width)          │  │  │ ◄─ Scrollable
│ ├───────────────────────────────────────────────┤  │
│ │ Card 3...                                     │  │
│ └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Testing

- Verified build: `npm run build` passes
- Tested with multiple cards (3+) - proper scrolling maintained
- Verified modal confirmation appears before submission
- Confirmed IP Pools panel stays visible during scroll

## Related Work

- Built upon: `260306-domains-rule-cards` (card-based interface)
- Original design: `docs/plans/260306-domains-rule-cards-design.md`
