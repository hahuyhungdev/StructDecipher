/**
 * Shared Card component.
 */
interface CardProps {
  title: string;
  children: React.ReactNode;
}

export default function Card({ title, children }: CardProps) {
  return (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
        marginBottom: 12,
      }}
    >
      <h3 style={{ margin: "0 0 8px" }}>{title}</h3>
      {children}
    </div>
  );
}
