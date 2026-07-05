export function Card({ as: Tag = "div", interactive = false, padded = true, className = "", children, ...rest }) {
  return (
    <Tag
      className={[
        "card",
        interactive ? "card-interactive" : "",
        padded ? "" : "p-0",
        className,
      ].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </Tag>
  );
}
