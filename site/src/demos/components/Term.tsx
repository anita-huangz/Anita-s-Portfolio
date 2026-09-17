import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { lookupTerm } from "../glossary";

const GAP = 8;
const PANEL_WIDTH = 300;

/**
 * A jargon term with its definition one click away.
 *
 * Three decisions worth stating.
 *
 * **The definition is always in the accessibility tree**, in a visually hidden
 * span the trigger points at with `aria-describedby`. The popover is then
 * purely visual — a screen reader reads the explanation without anyone having
 * to discover that the word is clickable.
 *
 * **Click, not hover.** Hover-only tooltips do not exist on a touch screen and
 * cannot be reached from a keyboard. Hover opens it too, for mouse users, but
 * nothing is hover-*only*.
 *
 * **The panel is positioned fixed, not absolute.** These demos live inside a
 * scrolling modal with `overflow-y: auto`, which clips an absolutely positioned
 * child at the container edge; a fixed panel measured from the trigger and
 * clamped to the viewport cannot be cut off.
 */
export function Term({
  id,
  children,
}: {
  /** A glossary id, term, or alias — see `glossary.ts`. */
  id: string;
  /** Label to show. Defaults to the glossary's own term. */
  children?: React.ReactNode;
}) {
  const entry = lookupTerm(id);
  const descId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLSpanElement>(null);
  // Two bits, not one. Hovering previews the definition and leaving hides it
  // again; clicking *pins* it open so it survives the pointer moving away.
  // Collapsing these into a single `open` makes a mouse click open on
  // `mouseenter` and then immediately close on `click`, so the definition
  // flashes and vanishes -- which is exactly what happened.
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  const dismiss = () => {
    setPinned(false);
    setOpen(false);
  };

  // A term that is not in the glossary renders as plain text rather than a
  // trigger that explains nothing. `glossary.test.ts` makes it a test failure
  // so it cannot ship unnoticed.
  useEffect(() => {
    if (!entry && import.meta.env.DEV) {
      console.warn(`Term: no glossary entry for ${JSON.stringify(id)}`);
    }
  }, [entry, id]);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const place = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const height = panelRef.current?.offsetHeight ?? 160;
      const below = rect.bottom + GAP;
      // Flip above when there is not room below, and never overhang either edge.
      const top =
        below + height < window.innerHeight ? below : Math.max(GAP, rect.top - height - GAP);
      const left = Math.min(
        Math.max(GAP, rect.left),
        Math.max(GAP, window.innerWidth - PANEL_WIDTH - GAP),
      );
      setPos({ top, left });
    };
    place();
    // Re-measure once the panel has its real height.
    const raf = requestAnimationFrame(place);
    return () => cancelAnimationFrame(raf);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        dismiss();
        triggerRef.current?.focus();
      }
    };
    const onPointer = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!triggerRef.current?.contains(target) && !panelRef.current?.contains(target)) {
        dismiss();
      }
    };
    // Capture, so Escape closes the definition before the modal behind it.
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onPointer);
    // Scrolling moves the trigger out from under a fixed panel.
    window.addEventListener("scroll", dismiss, { capture: true, once: true });
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  if (!entry) return <>{children ?? id}</>;

  return (
    <span className="term-wrap">
      <button
        ref={triggerRef}
        type="button"
        className="term"
        aria-expanded={open}
        aria-describedby={descId}
        onClick={() => {
          if (pinned) dismiss();
          else {
            setPinned(true);
            setOpen(true);
          }
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={(e) => {
          // Keep it up if pinned, or if the pointer moved onto the panel.
          if (pinned) return;
          if (!panelRef.current?.contains(e.relatedTarget as Node)) setOpen(false);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          if (!pinned) setOpen(false);
        }}
      >
        {children ?? entry.term}
        <span className="term-mark" aria-hidden="true">
          ?
        </span>
      </button>

      <span id={descId} className="sr-only">
        {entry.term}. {entry.body} {entry.here ?? ""}
      </span>

      {open && (
        <span
          ref={panelRef}
          className="term-pop"
          role="presentation"
          style={pos ? { top: pos.top, left: pos.left } : { opacity: 0 }}
          onMouseLeave={() => {
            if (!pinned) setOpen(false);
          }}
        >
          <span className="term-pop-title">{entry.term}</span>
          <span className="term-pop-body">{entry.body}</span>
          {entry.here && <span className="term-pop-here">{entry.here}</span>}
        </span>
      )}
    </span>
  );
}
