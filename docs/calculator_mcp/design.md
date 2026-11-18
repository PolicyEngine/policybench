# The calculator over MCP: what exists, and the design of an MCP arm

Status, 2026-11-18: this pull request adds the package, the server and the
checks below. The arm exists only as this design. Nobody has called a model
for it and no server faces the internet; both wait for a decision.

## What exists

- `policybench_calculator.core`: the calculator the tool pilot gives a model,
  as a package. It is a verbatim copy of the one in
  `scripts/tool_pilot_argon.py`, because the v2 confirmatory runner pins that
  script to its treatment commit; `scripts/sync_calculator_core.py` writes the
  copy and `tests/test_calculator_core.py` fails when the two differ.
- `policybench_calculator.mcp_server`: an MCP server with one tool,
  `calculate_household`. It lists the name, description and input schema that
  `calculate_tool_schema` builds for an arm, runs each call in the pilot's
  worker pool on the board's pinned engine and reform, and answers with
  `json.dumps` of the result, the text the pilot's `add_tool_result` sends a
  model. It serves stdio, or Streamable HTTP on 127.0.0.1, and offers its
  engine, board, features and schema hash as the resource
  `policybench://calculator/provenance`.
- `policybench_calculator.mcp_client.McpToolCall`: a `tool_call` for
  `run_household` (arguments in, result and seconds out) over an MCP session.
- `scripts/replay_calculator_calls.py`: replays recorded calls through the
  harness's calculator and the package's, and with `--mcp` through the server.

## Two arms that the word "MCP" could mean

**A. The harness is the MCP client.** The harness lists the tool from the
server, offers it to the model as the same function tool as today, and sends
each call to the server through `McpToolCall`. The model receives the same
prompt and the same tool definition as in the function-tool arm, so the two
arms differ only by sampling noise. A paid run of this arm would measure
nothing that the replay does not already measure for free: the replay sends
the calls models really made through the server and compares every answer
with the function tool's.

**B. The provider's connector is the MCP client.** The request names the
server; the provider's own servers list its tools, show them to the model, run
the model's calls and return a finished response. This is the arm the October
plan named ("an MCP arm through the providers' MCP connectors"), and the only
one that can show a difference: the provider decides how the tool looks to the
model and when the loop ends.

The rest of this note designs arm B. Arm A needs no further work beyond a run
command, and the note recommends against paying for it.

## What the providers document

Read on 2026-11-18 from each provider's own documentation and, for litellm,
from the installed 1.88.1 source; a second reader then checked each claim
against the same sources. "Not found" means the pages do not say. Nothing in
this table comes from a call to a model.

| | OpenAI | Anthropic | Google |
|---|---|---|---|
| Where | Responses API only | Messages API, beta header `mcp-client-2025-11-20` | Interactions API (preview), not `generateContent` |
| Request | `tools: [{"type": "mcp", "server_label", "server_url", "allowed_tools", "require_approval": "never", "headers"}]` | `mcp_servers: [{"type": "url", "url", "name", "authorization_token"}]` plus `tools: [{"type": "mcp_toolset", "mcp_server_name"}]` | `tools: [{"type": "mcp_server", "name", "url", "headers", "allowed_tools"}]` |
| Who calls the server | OpenAI's servers; "any server on the public Internet" | Anthropic's servers, over https only | Google's servers |
| Transports | Streamable HTTP or HTTP/SSE | Streamable HTTP or SSE | Streamable HTTP only |
| What the response shows | `mcp_list_tools`, then one `mcp_call` per call with `arguments`, `output` and `error` | `mcp_tool_use` (input) and `mcp_tool_result` (content, `is_error`) blocks | `mcp_server_tool_call` and `mcp_server_tool_result` steps |
| Fee beyond tokens | None ("No additional fees apply per tool call") | None on the pricing page | None on the pricing page |
| Limit on calls | `max_tool_calls` exists; whether it counts MCP calls is not found | Not found; server tools pause a turn after 10 iterations (`pause_turn`), and whether MCP calls count toward that is not found | Not found |
| Models | "most recent models"; examples use GPT-6.2 Astra | The page lists Opus 5.5, Sonnet 5.5 and Haiku 5.5 | Unresolved: one page says Gemini 3 lacks remote MCP, another's example uses Gemini 3.8 Flash |
| Private route | Secure MCP Tunnel (`tunnel_id`); eligibility outside enterprise is not stated | MCP tunnels, a research preview with access by request | Not found |
| Through litellm 1.88.1 | `litellm.responses()` passes the tool and returns the items unchanged | `litellm.completion()` sends the deprecated 2025-04-04 header and leaves `mcp_tool_use` blocks out of the message it returns; call the `anthropic` SDK directly | Not on the harness's path |

Two details matter for the build. OpenAI's default for `require_approval` is
"always", so the request must set "never" or every call returns as an approval
request. And litellm 1.88.1 takes over any `server_url` of the form
`.../mcp/<segment>` for its own gateway, so the server's URL must end in `/mcp`.

## How a provider would reach the server

The server runs the engine in local worker processes. A provider's connector
needs a URL its servers can reach, so something must face the internet for as
long as a run lasts. The household set is not public, and the calls carry the
facts a model wrote from it; the model's provider already receives those facts
in the prompt, and any host or tunnel between the provider and the server
would receive them too.

| Option | Set-up | Cost for about 3 hours | Who else sees the calls | Notes |
|---|---|---|---|---|
| Cloudflare tunnel from the run machine to the local server | Low | $0 | Cloudflare (it ends the TLS connection) | The engine and reform are the function arm's own install. The quick tunnel has no SSE (so the server must answer in plain JSON) and no uptime promise; a named tunnel needs a domain on Cloudflare. |
| Modal, an ASGI app with 2 to 4 warm workers | Medium | About $0.35 to $1.00 | Modal | PolicyEngine's usual host. Needs an image with the pinned engine and the reform; a request may run 150 seconds at most. |
| Cloud Run with minimum instances | Medium to high | About $0.35 to $1.40 | Google | Same image work as Modal. |
| The providers' own tunnels | Unknown | Not stated | The provider only | OpenAI's may need an enterprise organisation; Anthropic's needs an access request. Neither helps the other provider. |

Recommended for a development run: the Cloudflare tunnel, up only while the
run lasts, because it serves the very install the function arm used and needs
no image. Modal is the better choice if the arm ever runs at confirmatory
scale or from a machine that sleeps.

Whichever route a decision picks, the server needs four things it does not
have today. This pull request adds none of them, since no server may face the
internet yet:

1. A bearer token it checks on every request (OpenAI sends `headers` or
   `authorization`; Anthropic sends `authorization_token`; Google sends
   `headers`), and the SDK's host check opened to the tunnel's name only.
2. A token per household in the URL path or a header, so the server can tell
   one household's calls from another's.
3. Its own call log, one line per call: the household's token, the arguments
   as received, the result text, the seconds, and the protocol version the
   connector negotiated.
4. A limit on calls per household (see the next section).

## Keeping the treatment the same, and where it cannot be

- **The tool.** The server builds its listing from the same code as the
  function tool, and the tests check that every field matches. On a
  2025-era MCP connection the SDK's schema model puts the input schema's
  top-level keys in another order (`properties`, `required`, `type`; read
  from the SDK's source, not yet observed on the wire); the content is equal.
  How a provider then shows the tool to the model is not documented: OpenAI
  carries a `server_label` beside the name and has no `strict` setting for
  an MCP tool; Anthropic offers no strict setting on `mcp_toolset` either.
  The request must leave OpenAI's optional `server_description` unset, since
  the function arm has no such text.
- **The notice.** The arm sends the pe3 notice unchanged, including "You may
  call it in up to 8 turns".
- **The answer.** A tool-contract model (GPT-6) still answers through
  `submit_outputs`, an ordinary function the harness handles; a JSON-contract
  model (Claude Opus 5.5) still answers in its JSON reply.
- **Results and errors.** The server returns every result, a validation or
  engine error included, as ordinary text with `isError` unset, so the model
  reads the same text as in the function arm. (OpenAI's call item has an
  `error` field apart from `output` for failed calls; the pages do not say
  what the model sees for a result the server marks as an error, so the
  server marks none.)
- **The limits. This is the real difference.** The harness allows 8 tool
  turns and 4 calculations in a turn, answers a fifth with `not_run`, and
  then forces the answer. A connector runs the model's calls inside one
  response, so the harness cannot count turns or refuse a call. The server
  would enforce the largest number of calls the function arm permits a
  household, 32, and answer any further call with the harness's own `not_run`
  text. Turns have no equivalent. The development runs give the scale: pe3
  households made 1.5 to 4.8 calls on average by model, never more than 2 in
  a turn, and only Claude Haiku 5.5 reached the 8-turn limit (5 of 20
  households). The write-up must report calls per household for both arms.
- **Arguments.** A connector sends arguments as a JSON object, so the
  function arm's "arguments are not valid JSON" refusals cannot occur.

## Recording a household so that score and diagnose still work

`score` and `diagnose` read a household record's `turns[].calls[]` entries
(`name`, `arguments`, `result`, `tool_latency_seconds`), its predictions and
its treatment fields (`arm`, `tool_features`, `tool_notice_sha256`,
`calculate_tool_sha256`). The arm's runner writes the same record:

- one call entry per connector call item, with `arguments` as the provider
  reports them and `result` parsed from the output text;
- `tool_latency_seconds`, and a check of every argument and result, from the
  server's own log for that household's token, which is the authority when
  the two disagree;
- `arm: "pe3"` and the pe3 hashes, since the notice and the schema are pe3's,
  with a new field naming the transport, in an output folder of its own
  (`runs/<model>/mcp-pe3/`). The pinned script should then score and diagnose
  the folder as it stands, with no change to `scripts/tool_pilot_argon.py`;
  the build confirms that on fake connector responses before any paid call.

The runner is a new script beside the harness. It reuses the harness's prompt,
request settings, answer parsing and cost code by import, and replaces only
the conversation loop: for OpenAI one `responses` request per household, plus
repairs; for Anthropic the `anthropic` SDK's `beta.messages.create`, continued
after each `pause_turn`. A server that stops answering must end the household
with a rerunnable status, never a scored one.

## The run

- **Households and pairing.** The 20 development households (`mt_000` to
  `mt_019`; 10 for the frontier models, as before), with the v2-pilot prompt
  on policyengine-us 2.60.4, paired with the pe3 records already on disk.
  These are development data: the run is exploratory and stays out of the
  confirmatory study.
- **Models.** GPT-6 Luna and GPT-6 Sol through OpenAI's connector; Claude
  Haiku 5.5 and Claude Opus 5.5 through Anthropic's. Gemini waits: its
  connector lives in another API than the function arm uses, and the pages
  disagree on which models support it.
- **Measures.** Exact-match by output, paired by household, MCP against
  function, with the bootstrap the pilot's `score` already runs; calls per
  household; and a mechanical check that sends every call the arm recorded
  through the function tool and expects the same text.
- **First, a probe.** One household on GPT-6 Luna and one on Claude Haiku 5.5
  (under one cent at the measured means) settles what the pages leave open:
  whether
  `max_tool_calls` counts MCP calls, whether `tool_choice: "required"` accepts
  an MCP call, which protocol version each connector speaks, and how each
  shows the tool's name.

## Cost

Model spend, from the development runs' own records (list prices rebuilt from
token counts; mean per household in the pe3 arm):

| Model | Per household | Households | Estimate |
|---|---:|---:|---:|
| GPT-6 Luna | $0.0024 | 20 | $0.05 |
| GPT-6 Sol | $0.0544 | 10 | $0.54 |
| Claude Haiku 5.5 | $0.0041 | 20 | $0.08 |
| Claude Opus 5.5 | $0.0905 | 10 | $0.91 |
| **Four models** | | | **$1.58** |
| Gemini 3.5 Flash-Lite, if added | $0.0144 | 20 | $0.29 |
| Gemini 4 Argon, if added | $0.0554 | 10 | $0.55 ($1.11 from 1 December, when its price doubles) |

Neither OpenAI nor Anthropic documents a fee for an MCP call; tool listings
and results bill as input tokens, as a function tool's do. A connector may
loop differently from the harness, and a first run needs reruns, so the
request is a cap of **$10 at list prices** for the four models, probe included.
Hosting adds nothing for a tunnel and about a dollar on Modal.

## What a go would start

1. The server additions above (token, per-household path, call log, call
   limit), with tests, and the tunnel or Modal app.
2. The runner script and its record adapter, tested against recorded
   connector responses before any paid call.
3. The two-household probe, then the run, then `score` and `diagnose` on the
   new folder beside the pe3 one.
