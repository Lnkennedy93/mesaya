export default function Powered({ style }: { style?: React.CSSProperties }) {
  return (
    <div className="powered" style={style}>
      Desarrollado por{" "}
      <a href="https://www.nexflowlabs.co/" target="_blank" rel="noopener">
        Nexflow Labs
      </a>
    </div>
  );
}
