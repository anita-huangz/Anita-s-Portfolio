interface Props {
  caption: string;
  text: string;
}

/** Real captured output, framed as a terminal. */
export function Terminal({ caption, text }: Props) {
  return (
    <figure className="terminal" style={{ margin: 0 }}>
      <div className="terminal-bar">
        <span className="b" style={{ background: "#ff5f57" }} />
        <span className="b" style={{ background: "#febc2e" }} />
        <span className="b" style={{ background: "#28c840" }} />
        <figcaption className="cap">{caption}</figcaption>
      </div>
      <pre>{text}</pre>
    </figure>
  );
}
