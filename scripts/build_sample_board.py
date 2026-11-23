"""Build data/sample/sample_board.json from the sample lecture, checking every quote against the text.
    python scripts/build_sample_board.py
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.materials import extract
from app.writer import quote_in_passage

SRC = ROOT / "data" / "sample" / "ai_agents_lecture.md"
CLUES = {
 "Agent Basics": [
  (1, "This kind of AI system is a language model that can call tools in a loop until it finishes a task.", "an AI agent", ["agent", "AI agent"], "An AI agent is a language model that can call tools in a loop until it finishes a task."),
  (2, "A tool is described by a name, a description, and one of these for its arguments.", "a JSON schema", ["JSON schema", "schema"], "described by a name, a description, and a JSON schema for its arguments"),
  (3, "The model never runs a tool itself; this does, which is where permissions and logging belong.", "the surrounding code", ["code", "the code", "the program"], "The model never runs the tool itself; the surrounding code does, which is where permissions and logging belong."),
  (4, "Forcing a model to return data that fits a schema, like a Pydantic model, is called this.", "structured output", ["structured outputs"], "Structured output means the model must return data that fits a schema, such as a Pydantic model."),
  (5, "Structured output lets code check the answer this way instead of parsing free text.", "field by field", ["field-by-field"], "This lets code check the answer field by field instead of parsing free text."),
 ],
 "Protocol Droids": [
  (1, "This open standard, abbreviated MCP, lets an agent discover and call tools exposed by a server.", "the Model Context Protocol", ["Model Context Protocol"], "The Model Context Protocol, or MCP, is an open standard that lets an agent discover and call tools exposed by a server."),
  (2, "A local MCP server communicates over this channel.", "stdio", ["standard input/output", "standard io"], "An MCP server can run locally over stdio or remotely over HTTP."),
  (3, "A remote MCP server communicates over this protocol.", "HTTP", ["https"], "An MCP server can run locally over stdio or remotely over HTTP."),
  (4, "With the database behind an MCP server, agents can only touch data through these.", "the tools the server exposes", ["tools", "the server's tools", "exposed tools"], "agents can only touch data through the tools the server chooses to expose"),
  (5, "A good MCP tool returns only what is in the data and never does this to values.", "invents them", ["invent", "invents", "invent values", "makes them up"], "A good MCP tool returns only what is actually in the data and never invents values."),
 ],
 "Token Economy": [
  (1, "Providers bill by the number of input and output these.", "tokens", ["token"], "providers bill by the number of input and output tokens"),
  (2, "Roughly, one token is about this many characters of English.", "three to four", ["3 to 4", "3-4", "three or four"], "roughly three to four characters of English"),
  (3, "These tokens usually cost several times more than input tokens.", "output tokens", ["output"], "Output tokens usually cost several times more than input tokens."),
  (4, "Cached input tokens are often billed at this fraction of the normal input price.", "one tenth", ["1/10", "a tenth", "10 percent", "10%"], "often one tenth of the normal input price"),
  (5, "To benefit from caching, long static content goes here in the prompt.", "at the start", ["the start", "the beginning", "at the beginning", "first"], "put the long static content, such as instructions and a handbook, at the start of the prompt"),
 ],
 "Injection Protection": [
  (1, "This attack hides instructions inside data so that a model treats them as commands.", "prompt injection", ["injection"], "Prompt injection is an attack that hides instructions inside data so that a model treats them as commands."),
  (2, "Text of this color in a PDF is a classic place to hide an injection.", "white", ["white text"], "Examples include white text in a PDF"),
  (3, "In layered defense, this layer removes hidden text before any model sees it.", "the code layer", ["code", "code layer"], "The code layer removes hidden text before any model sees it"),
  (4, "Requiring every reported fact to be traceable to the source is called this.", "grounding", ["grounded"], "Grounding means every fact an agent reports must be traceable to the source."),
  (5, "Deliberately attacking your own system to find weaknesses before real users do.", "red teaming", ["red team", "red-teaming"], "Red teaming means deliberately attacking your own system to find weaknesses before real users do."),
 ],
}
FINAL = ("Many Hands", "In the safest design, agents may request money movements, but only these get the tool that actually moves the money.", "humans", ["people", "a human", "human"], "The safest design lets agents request money movements but gives only humans the tool that actually moves the money.")

def main():
    ex = extract([{"name": "ai_agents_lecture.md", "text": SRC.read_text()}])
    for p in ex.passages:
        p.source = "Sample lecture: Building AI Agents"
    def find(quote):
        best = max(ex.passages, key=lambda p: quote_in_passage(quote, p.text))
        score = quote_in_passage(quote, best.text)
        assert score >= 0.99, f"quote not in material: {quote}"
        return best
    cats = []
    for name, items in CLUES.items():
        clues = []
        for i, (d, clue, ans, acc, quote) in enumerate(items):
            p = find(quote)
            clues.append({"category": name, "clue": clue, "answer": ans, "accept": [ans] + acc, "difficulty": d,
                          "value": 200 * (i + 1), "passage": p.id, "source": p.source, "quote": quote,
                          "status": "ok", "verdict": "SUPPORTED", "note": ""})
        cats.append({"name": name, "clues": clues, "spares": []})
    c, clue, ans, acc, quote = FINAL
    p = find(quote)
    final = {"category": c, "clue": clue, "answer": ans, "accept": [ans] + acc, "difficulty": 3, "passage": p.id,
             "source": p.source, "quote": quote, "status": "ok"}
    board = {"title": "Building AI Agents (sample)", "categories": cats, "final": final, "values": [200, 400, 600, 800, 1000]}
    out = ROOT / "data" / "sample" / "sample_board.json"
    out.write_text(json.dumps(board, indent=1))
    print(f"wrote {out.relative_to(ROOT)}: {sum(len(c['clues']) for c in cats)} clues, all quotes verified")

if __name__ == "__main__":
    main()
