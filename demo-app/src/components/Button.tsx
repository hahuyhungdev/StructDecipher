/**
 * Shared Button component used across features.
 */
interface ButtonProps {
  label: string;
  onClick: () => void;
  variant?: "primary" | "secondary";
}

export default function Button({
  label,
  onClick,
  variant = "primary",
}: ButtonProps) {
  const bg = variant === "primary" ? "#4F46E5" : "#374151";
  return (
    <button
      onClick={onClick}
      style={{
        padding: "8px 16px",
        background: bg,
        color: "#fff",
        border: "none",
        borderRadius: 6,
        cursor: "pointer",
        fontSize: 14,
      }}
    >
      {label}
    </button>
  );
}
