"use client";

/**
 * Tip — small ⓘ icon with hover tooltip.
 * Usage:  <Tip text="WACC = borrowing cost..." />
 * Renders inline; wraps with position:relative so tooltip stays near icon.
 */

import { useState, useRef, useCallback } from "react";

interface TipProps {
  /** Tooltip text — keep under ~120 chars for best display. */
  text: string;
  /** Optional: override icon character (default ⓘ) */
  icon?: string;
  /** Optional: tooltip max-width in px (default 240) */
  width?: number;
}

export function Tip({ text, icon = "ⓘ", width = 240 }: TipProps) {
  const [show, setShow] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  const open  = useCallback(() => setShow(true),  []);
  const close = useCallback(() => setShow(false), []);

  return (
    <span
      ref={ref}
      style={{ position: "relative", display: "inline-flex", alignItems: "center", verticalAlign: "middle" }}
    >
      {/* Trigger icon */}
      <span
        onMouseEnter={open}
        onMouseLeave={close}
        onFocus={open}
        onBlur={close}
        onClick={e => { e.stopPropagation(); setShow(s => !s); }}
        tabIndex={0}
        role="button"
        aria-label="More info"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 11,
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

      {/* Tooltip bubble */}
      {show && (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            bottom: "calc(100% + 7px)",
            left: "50%",
            transform: "translateX(-50%)",
            width,
            background: "#1c1f1a",
            color: "#f0ede8",
            fontSize: 11.5,
            lineHeight: 1.55,
            padding: "8px 12px",
            borderRadius: 8,
            boxShadow: "0 4px 16px rgba(0,0,0,0.22)",
            zIndex: 9999,
            pointerEvents: "none",
            whiteSpace: "normal",
            // Arrow
            // We use ::after hack via inline but that needs CSS-in-JS — skip for simplicity.
          }}
        >
          {text}
          {/* Small caret */}
          <span style={{
            position: "absolute",
            bottom: -5,
            left: "50%",
            transform: "translateX(-50%)",
            width: 10,
            height: 10,
            background: "#1c1f1a",
            clipPath: "polygon(0 0, 100% 0, 50% 100%)",
          }} />
        </span>
      )}
    </span>
  );
}
