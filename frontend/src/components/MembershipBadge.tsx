"use client";

const MEMBERSHIP_STYLES: Record<string, { label: string; color: string; icon: string }> = {
  none: { label: "", color: "#9CA3AF", icon: "" },
  basic: { label: "Basic", color: "#22C55E", icon: "●" },
  standard: { label: "Standard", color: "#F59E0B", icon: "★" },
  premium: { label: "Premium", color: "#A855F7", icon: "♛" },
};

interface MembershipBadgeProps {
  type: string;
  size?: "sm" | "md";
}

export default function MembershipBadge({ type, size = "sm" }: MembershipBadgeProps) {
  const style = MEMBERSHIP_STYLES[type] || MEMBERSHIP_STYLES.none;

  if (type === "none") return null;

  const isSm = size === "sm";

  return (
    <span
      className="inline-flex items-center gap-1 font-medium"
      style={{
        color: style.color,
        fontSize: isSm ? "11px" : "13px",
        background: `${style.color}15`,
        border: `1px solid ${style.color}30`,
        borderRadius: "4px",
        padding: isSm ? "1px 6px" : "2px 8px",
      }}
    >
      <span style={{ fontSize: isSm ? "10px" : "12px" }}>{style.icon}</span>
      {style.label}
    </span>
  );
}
