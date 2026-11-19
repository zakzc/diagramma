import { EditorView } from "@codemirror/view";
import CodeMirror from "@uiw/react-codemirror";
import { mermaid } from "codemirror-lang-mermaid";
import { useSystemDark } from "../hooks/useMediaQuery";

const extensions = [mermaid(), EditorView.lineWrapping];

export default function CodePane({ value, onChange }: { value: string; onChange: (text: string) => void }) {
  const dark = useSystemDark();
  return (
    <div className="h-full overflow-auto text-sm" aria-label="Mermaid code editor">
      <CodeMirror
        value={value}
        onChange={onChange}
        theme={dark ? "dark" : "light"}
        extensions={extensions}
        basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: false }}
        minHeight="100%"
        style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
      />
    </div>
  );
}
