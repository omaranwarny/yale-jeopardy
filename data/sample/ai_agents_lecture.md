# Building AI Agents: Lecture Notes (sample material)

## 1. What is an agent?
An AI agent is a language model that can call tools in a loop until it finishes a task. Each turn, the model reads the conversation, decides whether to call a tool or to answer, and the program runs the tool and sends the result back.

A tool is a function the model can request, described by a name, a description, and a JSON schema for its arguments. The model never runs the tool itself; the surrounding code does, which is where permissions and logging belong.

Structured output means the model must return data that fits a schema, such as a Pydantic model. This lets code check the answer field by field instead of parsing free text.

## 2. The Model Context Protocol
The Model Context Protocol, or MCP, is an open standard that lets an agent discover and call tools exposed by a server. An MCP server can run locally over stdio or remotely over HTTP.

Because the database sits behind an MCP server, agents can only touch data through the tools the server chooses to expose. A good MCP tool returns only what is actually in the data and never invents values.

## 3. Multi-agent systems
In a multi-agent system, a coordinating agent delegates subtasks to specialist agents, each with its own prompt and tools. Delegation keeps each prompt short and focused, but every hand-off adds tokens and latency.

A human-in-the-loop step means a person must approve an action, such as a payment, before the code carries it out. The safest design lets agents request money movements but gives only humans the tool that actually moves the money.

## 4. Tokenomics
A token is a chunk of text, roughly three to four characters of English, and providers bill by the number of input and output tokens. Output tokens usually cost several times more than input tokens.

Prompt caching lets a provider reuse an identical prefix from an earlier request. Cached input tokens are billed at a steep discount, often one tenth of the normal input price, while writing the cache can cost slightly more than normal input.

To benefit from caching, put the long static content, such as instructions and a handbook, at the start of the prompt and the changing content, such as the user's document, at the end.

## 5. Prompt injection
Prompt injection is an attack that hides instructions inside data so that a model treats them as commands. Examples include white text in a PDF, an HTML comment, or a line of text drawn in a one-point font.

A strong defense works in layers. The code layer removes hidden text before any model sees it, the design layer keeps dangerous tools out of reach and lets code make the final decision, and the prompt layer tells the model that documents are data, not instructions.

Grounding means every fact an agent reports must be traceable to the source. A verifier can drop any number that does not appear in the visible document.

## 6. Evaluation
An evaluation set is a collection of inputs with known correct outputs, used to measure an agent before and after a change. Red teaming means deliberately attacking your own system to find weaknesses before real users do.
