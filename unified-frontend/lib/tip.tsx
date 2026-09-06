"use client";

/**
 * Tip — small ⓘ icon with hover tooltip.
 * Usage:  <Tip text="WACC = borrowing cost..." />
 * Renders inline; wraps with position:relative so tooltip stays near icon.
 *
 * Rendered via a React portal into document.body, positioned with
 * getBoundingClientRect(). This is deliberate: a plain position:absolute
 * bubble gets clipped by any ancestor with overflow:hidden/auto (KPI cards,
 * scrollable sidebars, etc.) and silently disappears behind neighbouring
 * elements. Portaling to <body> with a fixed position sidesteps every
 * ancestor's overflow/stacking context, so the tooltip is always fully
 * visible regardless of where <Tip> is used.
 */

import { useState, useRef, useCallback, useLayoutEffect, useEffect } from "react";
import { createPortal } from "react-dom";

interface TipProps {
  /** Tooltip text — keep under ~120 chars for best display. */
  text: string;
  /** Optional: override icon character (default ⓘ) */
  icon?: string;
  /** Optional: tooltip max-width in px (default 240) */
  width?: number;
}

const MARGIN = 8; // viewport-edge clearance

export function Tip({ text, icon = "ⓘ", width = 240 }: TipProps) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; caretLeft: number; flip: boolean } | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);

  const reposition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const anchorX = r.left + r.width / 2;

    // Clamp horizontally so the bubble never runs off-screen.
    const half = width / 2;
    let left = anchorX - half;
    left = Math.max(MARGIN, Math.min(left, window.innerWidth - width - MARGIN));
    const caretLeft = anchorX - left; // caret stays under the icon even when bubble is clamped

    // Prefer above the icon; flip below if there isn't room.
    const spaceAbove = r.top;
    const flip = spaceAbove < 90; // rough bubble height + arrow + margin
    const top = flip ? r.bottom + 9 : r.top - 9;

    setPos({ top, left, caretLeft, flip });
  }, [width]);

  const open = useCallback(() => { reposition(); setShow(true); }, [reposition]);
  const close = useCallback(() => setShow(false), []);

  useLayoutEffect(() => {
    if (!show) return;
    reposition();
  }, [show, reposition]);

  useEffect(() => {
    if (!show) return;
    const onScrollOrResize = () => reposition();
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [show, reposition]);

  return (
    <span
      ref={triggerRef}
      style={{ position: "relative", display: "inline-flex", alignItems: "center", verticalAlign: "middle" }}
    >
      {/* Trigger icon */}
      <span
        onMouseEnter={open}
        onMouseLeave={close}
        onFocus={open}
        onBlur={close}
        onClick={e => { e.stopPropagation(); setShow(s => !s); if (!show) reposition(); }}
        tabIndex={0}
        role="button"
        aria-label="More info"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 15,
          height: 15,
          fontSize: 12.5,
          lineHeight: 1,
          color: "#9ca3af",
          cursor: "help",
          userSelect: "none",
          marginLeft: 4,
          transition: "color 100ms",
          outline: "none",
        }}
        onMouseDown={e => e.preventDefault()}
      >
        {icon}
      </span>

      {/* Tooltip bubble — portaled to <body>, position:fixed so no ancestor
          (overflow:hidden card, scroll container, sticky sidebar, ...) can
          clip or bury it. */}
      {show && pos && typeof document !== "undefined" && createPortal(
        <span
          role="tooltip"
          style={{
            position: "fixed",
            top: pos.top,
            left: pos.left,
            transform: pos.flip ? "none" : "translateY(-100%)",
            width,
            maxWidth: `calc(100vw - ${MARGIN * 2}px)`,
            background: "#1c1f1a",
            color: "#f0ede8",
            fontSize: 12,
            lineHeight: 1.55,
            padding: "8px 12px",
            borderRadius: 8,
            boxShadow: "0 6px 20px rgba(0,0,0,0.28)",
            zIndex: 100000,
            pointerEvents: "none",
            whiteSpace: "normal",
          }}
        >
          {text}
          {/* Small caret pointing at the trigger icon */}
          <span style={{
            position: "absolute",
            ...(pos.flip ? { top: -5 } : { bottom: -5 }),
            left: pos.caretLeft,
            transform: "translateX(-50%) rotate(45deg)",
            width: 9,
            height: 9,
            background: "#1c1f1a",
          }} />
        </span>,
        document.body
      )}
    </span>
  );
}
